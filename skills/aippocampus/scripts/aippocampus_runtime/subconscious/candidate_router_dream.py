"""Dream-hypothesis foreground eligibility for subconscious routing.

Dream hypotheses are useful working-memory candidates, but they are not source
facts. Keep the review/trust-horizon gate out of the general router so future
candidate-routing changes do not accidentally loosen the foreground boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aippocampus_runtime.dream import constructive_outputs as dream_constructive
from aippocampus_runtime.source.io_kernel import parse_utc

DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"

ADJUDICATED_DREAM_STATES = (
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
)


def dream_horizon_timestamps(row: dict[str, Any], key: str) -> list[datetime]:
    horizon = row.get("trust_horizon") or {}
    invitation = row.get("prospective_invitation") or {}
    values = (
        row.get(key),
        horizon.get(key) if isinstance(horizon, dict) else None,
        invitation.get(key) if isinstance(invitation, dict) else None,
    )
    return [parsed for value in values if (parsed := parse_utc(str(value or "")))]


def dream_hypothesis_block_reason(row: dict[str, Any]) -> str:
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        return ""
    if str(row.get("review_state") or "") not in ADJUDICATED_DREAM_STATES:
        return "not_adjudicated"
    if (row.get("sensitive_use_gate") or {}).get("state") == "blocked" or row.get("human_review_required"):
        return "sensitive_review_required"
    now = datetime.now(timezone.utc)
    for key, reason in (
        ("expires_at", "dream_hypothesis_expired"),
        ("review_after", "trust_horizon_review_due"),
    ):
        if any(timestamp <= now for timestamp in dream_horizon_timestamps(row, key)):
            return reason
    invitation_block_reason = dream_constructive.prospective_invitation_block_reason(row)
    if invitation_block_reason:
        return invitation_block_reason
    return ""
