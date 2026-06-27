from __future__ import annotations

from typing import Any, Mapping

from guard_registry import compact_output_budget_for_guard


def compact_report(report: Mapping[str, Any], *, detail_command: str) -> dict[str, Any]:
    findings = list(report.get("findings") or [])
    blockers = [
        {
            "rule_id": item.get("rule_id"),
            "path": item.get("path") or item.get("file"),
            "line": item.get("line"),
            "owner_issue": item.get("owner_issue"),
            "message": item.get("message") or item.get("description"),
        }
        for item in findings
        if item.get("baseline_status") != "baselined"
        and item.get("changed_surface") is True
    ]
    return {
        "kind": report.get("kind"),
        "schema_version": report.get("schema_version"),
        "ok": report.get("ok"),
        "status": "pass" if report.get("ok") else "fail",
        "gate_class": "advisory" if report.get("advisory") else "hard",
        "verification_owner": "local_fail_fast",
        "guard_id": "agent-slop-guard",
        "owner_doc": "docs/architecture/ops/guard-lifecycle-registry.md",
        "gate_status": report.get("gate_status"),
        "advisory": report.get("advisory"),
        "mode": report.get("mode"),
        "scanned_file_count": report.get("scanned_file_count"),
        "finding_count": report.get("finding_count"),
        "changed_surface_unbaselined_count": report.get("changed_surface_unbaselined_count"),
        "fixture_failure_count": report.get("fixture_failure_count"),
        "blockers": blockers,
        "compact_output_budget": compact_output_budget_for_guard("agent-slop-guard"),
        "detail_command": detail_command,
        "policy": (
            "Compact output omits rule catalogs and owner-layer contracts. "
            "Use the detail command for full diagnostics."
        ),
    }
