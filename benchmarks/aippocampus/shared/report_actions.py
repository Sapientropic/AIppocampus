"""Small shared action cards for benchmark/readout reports."""

from __future__ import annotations

from typing import Any

BENCHMARK_CONTRACT_ISSUE_URL = "https://github.com/Sapientropic/AIppocampus/issues/2100"
BENCHMARK_SUITE_OWNER_PATH = "benchmarks/aippocampus/benchmark_suite.py"


def report_next_action(
    *,
    action_id: str,
    label: str,
    reason: str,
    command: str | None = None,
    owner_path: str | None = None,
    doc_path: str | None = None,
    required_artifact: str | None = None,
    issue_url: str | None = None,
    issue_state: str | None = None,
    no_action_reason: str | None = None,
    no_open_followup_reason: str | None = None,
    status: str = "actionable",
    claim_boundary: str = "diagnostic_action_not_source_evidence",
) -> dict[str, Any]:
    """Return a compact machine-usable action without pretending diagnostics are proof."""

    action: dict[str, Any] = {
        "id": action_id,
        "label": label,
        "status": status,
        "reason": reason,
        "mutation_risk": "read_only_or_review_only",
        "claim_boundary": claim_boundary,
    }
    if command:
        action["command"] = command
    if owner_path:
        action["owner_path"] = owner_path
    if doc_path:
        action["doc_path"] = doc_path
    if required_artifact:
        action["required_artifact"] = required_artifact
    action["issue_url"] = issue_url or BENCHMARK_CONTRACT_ISSUE_URL
    if issue_state:
        action["issue_state"] = issue_state
    if no_action_reason:
        action["no_action_reason"] = no_action_reason
    if no_open_followup_reason:
        action["no_open_followup_reason"] = no_open_followup_reason
    return action


def benchmark_suite_contract_fields(
    *,
    profile: str,
    track_count: int,
    known_gap_count: int,
    cannot_claim_count: int,
    contract_lint_failure_count: int,
) -> dict[str, Any]:
    review_next_actions = [
        report_next_action(
            action_id="review_benchmark_contract_followup",
            label="Review benchmark follow-up contract",
            reason=(
                "Use #2100 when a high-signal benchmark suite or track reports "
                "metrics/cannot_claim boundaries without owner/action routing."
            ),
            command="gh issue view 2100 --comments",
            owner_path=BENCHMARK_SUITE_OWNER_PATH,
            issue_url=BENCHMARK_CONTRACT_ISSUE_URL,
            claim_boundary="suite_followup_action_not_quality_evidence",
        ),
        report_next_action(
            action_id="rerun_profile_with_full_report",
            label="Rerun selected benchmark profile with full report",
            reason="Open the full report before changing public claim posture from a compact summary.",
            command=f"python benchmarks/aippocampus/benchmark_suite.py --profile {profile} --json",
            owner_path=BENCHMARK_SUITE_OWNER_PATH,
            issue_url=BENCHMARK_CONTRACT_ISSUE_URL,
            claim_boundary="diagnostic_rerun_not_public_quality_claim",
        ),
    ]
    return {
        "benchmark_maturity_level": "diagnostic_suite",
        "measurement_origin": "scripted_proxy",
        "observed_agent_behavior": False,
        "decision_impact": "profile_scoped_diagnostic_only",
        "decision_impact_gate_ok": False,
        "case_count": int(track_count),
        "owner_path": BENCHMARK_SUITE_OWNER_PATH,
        "current_issue_url": BENCHMARK_CONTRACT_ISSUE_URL,
        "metrics": {
            "track_count": int(track_count),
            "known_gap_count": int(known_gap_count),
            "cannot_claim_count": int(cannot_claim_count),
            "contract_lint_failure_count": int(contract_lint_failure_count),
        },
        "supports": [
            "profile-scoped benchmark suite execution is available",
            "track-level contract lint results are reported before quality claims",
        ],
        "useful_now": [
            "choose the smallest benchmark profile that owns the claim under review",
            "use contract lint findings to route missing owner/action follow-up",
        ],
        "review_next_actions": review_next_actions,
    }
