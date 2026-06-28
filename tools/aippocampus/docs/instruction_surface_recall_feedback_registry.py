"""Recall feedback instruction-surface owner classifications."""

from __future__ import annotations

RECALL_FEEDBACK_INSTRUCTION_SURFACE_CLASSIFIED_FILES = {
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py": {
        "classification": "apw_fallback_projection_owner",
        "owner": "#2678/#2651",
        "why": (
            "owns APW fallback cards and deepen-request projection; policy gating "
            "lives in the focused sibling helper after the #2678 split"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback_policy.py": {
        "classification": "apw_fallback_policy_owner",
        "owner": "#2678/#2651",
        "why": (
            "owns APW fallback promotion and candidate-input gating; source-open "
            "proof remains in fallback/deepen follow-through, not policy text"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_inputs.py": {
        "classification": "apw_input_sidecar_owner",
        "owner": "#2635/#2636/#2651",
        "why": (
            "owns APW sidecar input-status and diagnostic wording; sidecars guide "
            "navigation only and source-open proof stays in deepen/open probes"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_walker.py": {
        "classification": "apw_navigation_policy_owner",
        "owner": "#2919/#2678/#2651",
        "why": (
            "owns bounded APW exploration and same-scope feedback policy; walker "
            "strings describe local navigation invariants, while canonical "
            "feedback signal meaning lives in recall.feedback.vocabulary"
        ),
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/feedback/vocabulary.py": {
        "classification": "feedback_vocabulary_owner",
        "owner": "#2919/#2651",
        "why": (
            "owns canonical route-feedback signals, aliases, polarity, and recall "
            "outcome adapters so APW, semantic recall, MCP feedback, and trace "
            "admission do not grow local taxonomies"
        ),
    },
}
