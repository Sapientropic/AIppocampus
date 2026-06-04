#!/usr/bin/env python3
"""Question-tracking prefilter observability.

The default question-tracking runtime still uses deterministic pair scan.
Optional sidecar/vector helpers are evaluation substrates until source-joined
parity and real-history cost evidence justify enabling an accelerated path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def question_tracking_prefilter_report(
    *,
    candidate_count: int,
    pair_count: int,
) -> dict[str, Any]:
    return {
        "mode": "pair_scan",
        "candidate_source": "subconscious_jobs_jsonl",
        "pair_generation": "all_trackable_pairs",
        "accelerated_prefilter": "disabled",
        "sidecar_status": "not_used",
        "vector_status": "not_used",
        "default_prefilter_enabled": False,
        "source_join_required_before_acceleration": True,
        "available_prefilter_evaluators": [
            "question_index_sidecar",
            "question_vector_index",
        ],
        "candidate_count": int(candidate_count),
        "trackable_pair_count": int(pair_count),
        "pair_count": int(pair_count),
        "truth_boundary": (
            "prefilter candidates are navigation hints until clean-source refs "
            "are rejoined"
        ),
    }


def question_tracking_prefilter_fields(
    input_diagnostics: Mapping[str, Any],
    link_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    report = question_tracking_prefilter_report(
        candidate_count=int(input_diagnostics.get("candidate_count") or 0),
        pair_count=int(link_diagnostics.get("pair_count") or 0),
    )
    return {
        "prefilter_mode": report["mode"],
        "question_tracking_prefilter": report,
    }
