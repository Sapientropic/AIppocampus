"""Source-backed agent learning loop.

The learning loop consumes scrubbed behavior/source-texture style rows and
emits review signals, candidates, and action-time guidance. It never stores raw
tool output, rewrites clean source, or grants claim authority.
"""

from aippocampus_runtime.learning_loop.aippo_adapter import (
    build_contract_from_learning_findings,
    build_learning_aippo_bridge_report,
    learning_findings_to_aippo_source_rows,
)
from aippocampus_runtime.learning_loop.core import (
    adapt_behavior_events_to_review_signals,
    build_learning_action_time_packet,
    build_learning_loop_dogfood_fixture_report,
    build_semantic_learning_hypotheses,
    detect_recurring_failure_findings,
    detect_workflow_order_findings,
    extract_learning_activations,
    extract_workflow_candidates,
    project_action_time_guidance,
    project_guidance_to_route_readiness,
)
from aippocampus_runtime.learning_loop.effectiveness_ledger import (
    apply_effectiveness_to_guidance,
    ledger_rows_from_guidance_outcomes,
    summarize_effectiveness_ledger,
)
from aippocampus_runtime.learning_loop.semantic_learning import (
    adjudicate_semantic_learning_hypotheses,
    build_semantic_learning_dogfood_fixture_report,
    build_semantic_learning_stage_report,
    intake_semantic_learning_hypotheses,
    summarize_semantic_learning_guidance_outcomes,
    surface_semantic_learning_guidance,
)

__all__ = [
    "adapt_behavior_events_to_review_signals",
    "apply_effectiveness_to_guidance",
    "build_contract_from_learning_findings",
    "build_learning_action_time_packet",
    "build_learning_aippo_bridge_report",
    "build_learning_loop_dogfood_fixture_report",
    "build_semantic_learning_dogfood_fixture_report",
    "build_semantic_learning_hypotheses",
    "build_semantic_learning_stage_report",
    "detect_recurring_failure_findings",
    "detect_workflow_order_findings",
    "extract_learning_activations",
    "extract_workflow_candidates",
    "intake_semantic_learning_hypotheses",
    "learning_findings_to_aippo_source_rows",
    "ledger_rows_from_guidance_outcomes",
    "project_action_time_guidance",
    "project_guidance_to_route_readiness",
    "adjudicate_semantic_learning_hypotheses",
    "summarize_semantic_learning_guidance_outcomes",
    "surface_semantic_learning_guidance",
    "summarize_effectiveness_ledger",
]
