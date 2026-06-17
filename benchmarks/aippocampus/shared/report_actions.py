"""Small shared action cards for benchmark/readout reports."""

from __future__ import annotations

from typing import Any


def report_next_action(
    *,
    action_id: str,
    label: str,
    reason: str,
    command: str | None = None,
    owner_path: str | None = None,
    required_artifact: str | None = None,
    issue_url: str | None = None,
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
    if required_artifact:
        action["required_artifact"] = required_artifact
    if issue_url:
        action["issue_url"] = issue_url
    return action
