"""Cognitive Observatory instruction-surface owner classifications."""

from __future__ import annotations

OBSERVATORY_INSTRUCTION_SURFACE_CLASSIFIED_FILES = {
    "skills/aippocampus/scripts/aippocampus_runtime/ops/cognitive_observatory_summary.py": {
        "classification": "cognitive_observatory_summary_owner",
        "owner": "#2912/#576/#2651",
        "why": (
            "owns Cognitive Observatory compact summary and panel-preview wording; "
            "operator proof and claim-boundary detail stay out of default output"
        ),
    },
    "tests/aippocampus/test_cognitive_observatory.py": {
        "classification": "cognitive_observatory_test_contract_owner",
        "owner": "#2912/#574/#575/#576/#2651",
        "why": (
            "owns Observatory compact/detail, redaction, and read-only fixture "
            "strings; tests guard foreground noise boundaries without becoming "
            "runtime instructions"
        ),
    },
}
