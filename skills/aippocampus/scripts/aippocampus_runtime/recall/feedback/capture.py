"""Low-authority recall feedback capture receipts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.agent_continuity_cli_support import policy_boundary
from aippocampus_runtime.recall.feedback import events as feedback_events
from aippocampus_runtime.recall.feedback.suppression_lifecycle import (
    HARD_NEGATIVE_SUPPRESSION_SIGNALS,
    PARKED_SUPPRESSION_SIGNALS,
)
from aippocampus_runtime.recall.semantic import cue_learning as semantic_cue_learning

SCHEMA_VERSION = "agent-continuity-path-v1"
KIND = "aippocampus_agent_continuity_path"


def capture_feedback(
    *,
    route_id: str,
    outcome: str,
    route_kind: str = "active_path",
    reason: str = "",
    feedback_path: str | Path | None = None,
    feedback_lane: Mapping[str, Any] | None = None,
    semantic_cues_path: str | Path | None = None,
    schema_version: str = SCHEMA_VERSION,
    kind: str = KIND,
) -> dict[str, Any]:
    """Capture low-authority outcome feedback without changing source truth."""

    event = feedback_events.active_flow_event(
        route_id=route_id,
        route_kind=route_kind,
        signal=outcome,
        source_id=route_id,
        reason=reason,
    )
    wrote_event = False
    if feedback_path:
        target = Path(feedback_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        wrote_event = True
    cue_demotion: dict[str, Any] | None = None
    if wrote_event and semantic_cues_path and (
        event["signal"] in HARD_NEGATIVE_SUPPRESSION_SIGNALS
        or event["signal"] in PARKED_SUPPRESSION_SIGNALS
        or event["signal"] == "expired"
    ):
        cue_demotion = semantic_cue_learning.demote_recall_cue_route(
            Path(semantic_cues_path).resolve(),
            route_id=route_id,
            reason=event["signal"],
        )
    report = feedback_events.recall_feedback_report([event])
    return redact_sensitive_values(
        redact_private_paths(
            {
                "kind": kind,
                "schema_version": schema_version,
                "mode": "feedback",
                "status": "captured",
                "authority": "low_authority_feedback_signal",
                "event": event,
                "feedback_lane": dict(feedback_lane or {}) if feedback_lane else None,
                "feedback_report": report,
                "semantic_cue_demotion": cue_demotion,
                "wrote_event": wrote_event,
                "storage": "jsonl" if wrote_event else "receipt_only",
                "policy_boundary": {
                    **policy_boundary(),
                    "feedback_is_source_truth": False,
                    "feedback_can_ripen_candidate_without_source": False,
                    "source_reopen_required_for_claims": True,
                },
                "red_lines": {
                    "feedback_promoted_without_source": 0,
                    "source_truth_changed_by_feedback": 0,
                },
            }
        )
    )
