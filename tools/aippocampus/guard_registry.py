from __future__ import annotations

import re
from typing import Any, Mapping

OWNER_DOC = "docs/architecture/ops/guard-lifecycle-registry.md"

GATE_CLASSES = frozenset({"hard", "advisory", "ci_owned", "manual_required"})
VERIFICATION_OWNERS = frozenset(
    {
        "local_fail_fast",
        "local_closeout",
        "ci_required",
        "manual_dogfood",
        "advisory",
    }
)
FIELD_CLASSES = frozenset(
    {
        "compact_contract",
        "detail_diagnostic",
        "trace_operator_only",
        "internal_only",
    }
)

COMMAND_METADATA_KEYS = (
    "gate_class",
    "verification_owner",
    "owner",
    "owner_doc",
    "guard_id",
    "cost_budget",
    "cost_budget_ms",
    "ci_owned",
    "ci_mirrored",
    "default_local",
    "acceptance_bearing",
    "phase",
    "compact_output_budget",
)

SCOPE_PHASES = {
    "worktree": "fail_fast",
    "static": "fail_fast",
    "architecture-debt": "red_light",
    "changed-surface-debt": "red_light",
    "changed-surface-advisory": "red_light",
    "focused": "focused",
    "advisory": "red_light",
    "diagnostic": "diagnostic",
    "public-boundary": "closeout",
    "pre-push": "closeout",
    "surface": "closeout",
    "sanity": "sanity",
    "decision": "closeout",
    "release-preflight": "closeout",
    "publish": "ci_required",
    "post-publish": "manual_dogfood",
}

SCOPE_GATE_DEFAULTS: dict[str, dict[str, Any]] = {
    "worktree": {
        "gate_class": "hard",
        "verification_owner": "local_fail_fast",
        "cost_budget": "tiny",
        "cost_budget_ms": 5_000,
        "guard_id": "git-diff-check",
    },
    "static": {
        "gate_class": "hard",
        "verification_owner": "local_fail_fast",
        "cost_budget": "small",
        "cost_budget_ms": 60_000,
        "guard_id": "static-parity",
        "ci_mirrored": True,
    },
    "architecture-debt": {
        "gate_class": "hard",
        "verification_owner": "local_fail_fast",
        "cost_budget": "small",
        "cost_budget_ms": 30_000,
        "guard_id": "architecture-debt-headroom",
    },
    "changed-surface-debt": {
        "gate_class": "hard",
        "verification_owner": "local_fail_fast",
        "cost_budget": "small",
        "cost_budget_ms": 45_000,
        "guard_id": "changed-surface-debt",
    },
    "changed-surface-advisory": {
        "gate_class": "advisory",
        "verification_owner": "local_fail_fast",
        "cost_budget": "small",
        "cost_budget_ms": 45_000,
        "guard_id": "agent-slop-guard",
        "acceptance_bearing": True,
    },
    "focused": {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "cost_budget": "medium",
        "cost_budget_ms": 180_000,
        "guard_id": "focused-unittest",
        "default_local": False,
    },
    "advisory": {
        "gate_class": "advisory",
        "verification_owner": "advisory",
        "cost_budget": "small",
        "cost_budget_ms": 45_000,
        "guard_id": "advisory-quality-report",
    },
    "diagnostic": {
        "gate_class": "advisory",
        "verification_owner": "advisory",
        "cost_budget": "tiny",
        "cost_budget_ms": 15_000,
        "guard_id": "tier-report-diagnostic",
        "acceptance_bearing": False,
    },
    "public-boundary": {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "cost_budget": "small",
        "cost_budget_ms": 60_000,
        "guard_id": "public-boundary",
    },
    "pre-push": {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "cost_budget": "medium",
        "cost_budget_ms": 300_000,
        "guard_id": "tier-pr",
        "ci_mirrored": True,
        "default_local": False,
    },
    "surface": {
        "gate_class": "ci_owned",
        "verification_owner": "ci_required",
        "cost_budget": "ci",
        "cost_budget_ms": 0,
        "guard_id": "benchmark-smoke-public-fast",
        "ci_owned": True,
        "default_local": False,
    },
    "sanity": {
        "gate_class": "hard",
        "verification_owner": "local_fail_fast",
        "cost_budget": "small",
        "cost_budget_ms": 90_000,
        "guard_id": "tier-quick",
        "ci_mirrored": True,
    },
    "decision": {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "cost_budget": "tiny",
        "cost_budget_ms": 15_000,
        "guard_id": "changed-surface-plan",
    },
    "release-preflight": {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "cost_budget": "small",
        "cost_budget_ms": 90_000,
        "guard_id": "release-preflight",
    },
    "publish": {
        "gate_class": "ci_owned",
        "verification_owner": "ci_required",
        "cost_budget": "ci",
        "cost_budget_ms": 0,
        "guard_id": "publish-workflow",
        "ci_owned": True,
        "default_local": False,
    },
    "post-publish": {
        "gate_class": "manual_required",
        "verification_owner": "manual_dogfood",
        "cost_budget": "manual",
        "cost_budget_ms": 0,
        "guard_id": "post-publish-install",
        "default_local": False,
    },
}

COMMAND_GUARD_PATTERNS: tuple[tuple[re.Pattern[str], dict[str, Any]], ...] = (
    (re.compile(r"^git diff --check(?:\s+.+\.\.HEAD)?$"), {"guard_id": "git-diff-check"}),
    (re.compile(r"^ruff check\b"), {"guard_id": "static-ruff"}),
    (re.compile(r"^mypy$"), {"guard_id": "static-mypy"}),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]docs[/\\]debt_report\.py\b.*--headroom-only"),
        {"guard_id": "architecture-debt-headroom"},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]docs[/\\]debt_report\.py\b.*--changed-surface-only"),
        {"guard_id": "changed-surface-debt"},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]agent_slop_guard\.py\b"),
        {"guard_id": "agent-slop-guard"},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]docs[/\\]check_docs_health\.py\b"),
        {"guard_id": "docs-health", "ci_mirrored": True},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--tier quick\b"),
        {"guard_id": "tier-quick", "ci_mirrored": True},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--tier pr\b"),
        {"guard_id": "tier-pr", "ci_mirrored": True},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--tier broad-pr\b"),
        {
            "guard_id": "tier-broad-pr",
            "gate_class": "ci_owned",
            "verification_owner": "ci_required",
            "cost_budget": "ci",
            "cost_budget_ms": 0,
            "ci_owned": True,
            "default_local": False,
        },
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--tier full\b"),
        {
            "guard_id": "tier-full-release",
            "gate_class": "ci_owned",
            "verification_owner": "ci_required",
            "cost_budget": "ci",
            "cost_budget_ms": 0,
            "ci_owned": True,
            "default_local": False,
        },
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--report-json\b"),
        {"guard_id": "tier-report-diagnostic", "gate_class": "advisory"},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]run_tests\.py\b.*--tier benchmark-smoke\b"),
        {
            "guard_id": "benchmark-smoke-public-fast",
            "gate_class": "ci_owned",
            "verification_owner": "ci_required",
            "cost_budget": "ci",
            "cost_budget_ms": 0,
            "ci_owned": True,
            "default_local": False,
        },
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]recall_integration_readiness\.py\b"),
        {
            "guard_id": "recall-integration-readiness",
            "gate_class": "hard",
            "verification_owner": "local_closeout",
            "cost_budget": "small",
            "cost_budget_ms": 90_000,
        },
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]navigation_data_quality_guard\.py\b"),
        {
            "guard_id": "navigation-data-quality",
            "gate_class": "advisory",
            "verification_owner": "advisory",
        },
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]release[/\\]check_public_boundary\.py\b"),
        {"guard_id": "public-boundary"},
    ),
    (
        re.compile(r"tools[/\\]aippocampus[/\\]release[/\\]check_agent_discovery_release\.py\b"),
        {"guard_id": "release-agent-discovery"},
    ),
)

GUARD_COMPACT_OUTPUT_BUDGETS: dict[str, dict[str, Any]] = {
    "changed-surface-preflight": {
        "profile": "foreground_compact",
        "max_top_level_keys": 24,
        "max_blockers": 1,
        "detail_mode": "--detail full",
    },
    "closeout-audit": {
        "profile": "foreground_compact",
        "max_top_level_keys": 16,
        "max_blockers": 1,
        "detail_mode": "--detail full or body-env audit rerun",
    },
    "agent-slop-guard": {
        "profile": "foreground_compact",
        "max_top_level_keys": 16,
        "max_blockers": 5,
        "detail_mode": "--detail full",
    },
    "changed-surface-debt": {
        "profile": "foreground_compact",
        "max_top_level_keys": 12,
        "max_blockers": 3,
        "detail_mode": "--detail full",
    },
    "tier-report-diagnostic": {
        "profile": "operator_detail",
        "max_top_level_keys": 0,
        "max_blockers": 0,
        "detail_mode": "--report-json",
    },
}

COMPACT_FIELD_CLASSIFICATIONS: dict[str, str] = {
    "kind": "compact_contract",
    "schema_version": "compact_contract",
    "ok": "compact_contract",
    "status": "compact_contract",
    "mode": "compact_contract",
    "summary": "compact_contract",
    "content": "compact_contract",
    "structuredContent": "compact_contract",
    "isError": "compact_contract",
    "changed_surface": "compact_contract",
    "changed_file_count": "compact_contract",
    "affected_files": "compact_contract",
    "affected_files_truncated": "compact_contract",
    "planned_command_count": "compact_contract",
    "mode_runnable_command_count": "compact_contract",
    "ran_command_count": "compact_contract",
    "skipped_command_count": "compact_contract",
    "skipped_by_mode_count": "compact_contract",
    "skipped_after_failure_count": "compact_contract",
    "warning_count": "compact_contract",
    "first_warning": "compact_contract",
    "warning_summary": "compact_contract",
    "blockers": "compact_contract",
    "first_blocker": "compact_contract",
    "first_failure": "compact_contract",
    "blocker_count": "compact_contract",
    "commands": "compact_contract",
    "skipped_commands": "compact_contract",
    "detail_command": "compact_contract",
    "closeout_command": "compact_contract",
    "preflight_command": "compact_contract",
    "planner_detail_command": "compact_contract",
    "next_commands": "compact_contract",
    "gate_class": "compact_contract",
    "verification_owner": "compact_contract",
    "guard_id": "compact_contract",
    "owner_doc": "compact_contract",
    "cost_budget": "compact_contract",
    "ci_owned": "compact_contract",
    "ci_mirrored": "compact_contract",
    "default_local": "compact_contract",
    "acceptance_bearing": "compact_contract",
    "phase": "compact_contract",
    "verification_cost": "compact_contract",
    "duplicate_run_budget": "compact_contract",
    "compact_output_budget": "compact_contract",
    "policy": "compact_contract",
    "advisory": "compact_contract",
    "gate_status": "compact_contract",
    "scanned_file_count": "compact_contract",
    "finding_count": "compact_contract",
    "changed_surface_unbaselined_count": "compact_contract",
    "fixture_failure_count": "compact_contract",
    "refresh_command": "compact_contract",
    "closing_issues": "compact_contract",
    "closeout_class": "compact_contract",
    "evidence_level": "compact_contract",
    "risk_terms": "compact_contract",
    "findings": "compact_contract",
    "stdout_tail": "compact_contract",
    "stderr_tail": "compact_contract",
    "error": "compact_contract",
    "elapsed_ms": "compact_contract",
    "returncode": "compact_contract",
    "command": "compact_contract",
    "scope": "compact_contract",
    "reason": "compact_contract",
    "action_id": "compact_contract",
    "auto_chained": "compact_contract",
    "auto_chain_status": "compact_contract",
    "deferred_auto_chain_reason": "compact_contract",
    "tool_name": "compact_contract",
    "arguments": "compact_contract",
    "claim_boundary": "compact_contract",
    "likely_cause": "compact_contract",
    "can_use_for": "compact_contract",
    "must_reopen_for": "compact_contract",
    "source_boundary": "compact_contract",
    "detail_available_with": "compact_contract",
    "warnings": "detail_diagnostic",
    "changed_files": "detail_diagnostic",
    "phase_plan": "detail_diagnostic",
    "skipped_by_mode": "detail_diagnostic",
    "duplicate_test_modules": "detail_diagnostic",
    "plan_categories": "detail_diagnostic",
    "python_environment": "detail_diagnostic",
    "rules": "detail_diagnostic",
    "owner_layer_contracts": "detail_diagnostic",
    "fixture_results": "detail_diagnostic",
    "baseline_policy": "detail_diagnostic",
    "evidence_shape": "trace_operator_only",
    "performance_evidence_shape": "trace_operator_only",
    "runtime_provenance": "trace_operator_only",
    "policy_matrix": "trace_operator_only",
    "selector_inventory": "trace_operator_only",
    "operator_detail_command": "trace_operator_only",
    "operator_detail_command_template": "trace_operator_only",
    "debug": "trace_operator_only",
    "cache": "trace_operator_only",
    "feedback_controls": "trace_operator_only",
    "raw": "internal_only",
    "rows": "internal_only",
    "internal": "internal_only",
}


def scope_base(scope: str) -> str:
    return str(scope or "unknown").split(":", 1)[0]


def phase_for_scope(scope: str) -> str:
    return SCOPE_PHASES.get(scope_base(scope), "focused")


def compact_output_budget_for_guard(guard_id: str) -> dict[str, Any]:
    return dict(GUARD_COMPACT_OUTPUT_BUDGETS.get(guard_id) or {})


def classify_compact_field(field: str) -> str | None:
    return COMPACT_FIELD_CLASSIFICATIONS.get(str(field or ""))


def compact_field_allowed(field: str) -> bool:
    return classify_compact_field(field) == "compact_contract"


def gate_metadata_for_command(command: str, scope: str) -> dict[str, Any]:
    base = scope_base(scope)
    metadata: dict[str, Any] = {
        "gate_class": "hard",
        "verification_owner": "local_closeout",
        "owner": "verification-steward",
        "owner_doc": OWNER_DOC,
        "guard_id": "focused-unittest",
        "cost_budget": "medium",
        "cost_budget_ms": 180_000,
        "ci_owned": False,
        "ci_mirrored": False,
        "default_local": True,
        "acceptance_bearing": True,
        "phase": phase_for_scope(scope),
        "compact_output_budget": "foreground_action_sized",
    }
    metadata.update(SCOPE_GATE_DEFAULTS.get(base, {}))
    for pattern, override in COMMAND_GUARD_PATTERNS:
        if pattern.search(command):
            metadata.update(override)
            break
    metadata["phase"] = phase_for_scope(scope)
    metadata["owner_doc"] = OWNER_DOC
    metadata["owner"] = "verification-steward"
    if metadata["gate_class"] not in GATE_CLASSES:
        metadata["gate_class"] = "hard"
    if metadata["verification_owner"] not in VERIFICATION_OWNERS:
        metadata["verification_owner"] = "local_closeout"
    return metadata


def decorate_command(command: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "command": str(command.get("command") or ""),
        "reason": str(command.get("reason") or ""),
        "scope": str(command.get("scope") or "unknown"),
    }
    row.update(gate_metadata_for_command(row["command"], row["scope"]))
    for key in COMMAND_METADATA_KEYS:
        if key in command and command[key] not in {None, ""}:
            row[key] = command[key]
    return row


def guard_registry_summary() -> dict[str, Any]:
    return {
        "owner_doc": OWNER_DOC,
        "gate_classes": sorted(GATE_CLASSES),
        "verification_owners": sorted(VERIFICATION_OWNERS),
        "guard_count": len({metadata["guard_id"] for metadata in SCOPE_GATE_DEFAULTS.values()}),
        "compact_output_budgets": GUARD_COMPACT_OUTPUT_BUDGETS,
        "field_classes": sorted(FIELD_CLASSES),
    }
