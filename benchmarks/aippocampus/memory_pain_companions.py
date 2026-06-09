"""Companion reports for public-safe memory-pain fixtures.

The main gate benchmark owns prompt-routing behavior. These side reports model
adjacent memory-system failure families that should travel with the benchmark
output without turning the runner into a registry of every new fixture module.
"""

from __future__ import annotations

from typing import Any, Callable

import auto_hook_pollution
import memory_hygiene
import note_memory_drift
from claim_boundary_refs import claim_boundary_ref

ReportRunner = Callable[..., dict[str, Any]]
COMPANION_CLAIM_BOUNDARY_REF = claim_boundary_ref(
    "docs/evidence/benchmarks/memory-pain-fixture-report.md"
)


COMPANION_REPORTS: tuple[tuple[str, ReportRunner], ...] = (
    ("memory_hygiene_fixtures", memory_hygiene.run_memory_hygiene_fixture_report),
    (
        "auto_hook_pollution_fixtures",
        auto_hook_pollution.run_auto_hook_pollution_fixture_report,
    ),
    ("note_memory_drift_fixtures", note_memory_drift.run_note_memory_drift_fixture_report),
)


def run_memory_pain_companion_reports(*, include_private_text: bool = False) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for report_key, runner in COMPANION_REPORTS:
        report = runner(include_private_text=include_private_text)
        report["claim_boundary_ref"] = COMPANION_CLAIM_BOUNDARY_REF
        reports[report_key] = report
    return reports


def companion_cannot_claim(reports: dict[str, Any]) -> list[str]:
    claims: list[str] = []
    for report in reports.values():
        if isinstance(report, dict):
            claims.extend(str(claim) for claim in report.get("cannot_claim") or [])
    return claims
