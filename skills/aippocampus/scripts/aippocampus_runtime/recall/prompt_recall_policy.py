#!/usr/bin/env python3
"""Named foreground prompt-recall routing policies.

These values control when the foreground hook stays quiet, emits a scent, or
asks for source-backed evidence. Keep them separate from `scoring_policy.py`:
retrieval scores rank source hits, while this module owns the user-visible
skip/scent/evidence boundary. Semantic and subconscious judgment must continue
to come from source-backed state and optional model review, not from expanding
static cue lists to chase benchmark cases.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class PromptRecallGatePolicy:
    scent_threshold: float = 5.0
    evidence_threshold: float = 10.0
    default_search_budget: int = 3
    max_context_chars: int = 1800
    scent_probe_limit: int = 8
    scent_probe_score_multiplier: float = 2.4
    scent_probe_score_cap: float = 32.0
    evidence_lite_min_probe_score: float = 6.0
    life_wide_timeline_candidate_limit: int = 3
    explicit_recall_bonus: float = 4.0
    associative_cue_cap: float = 4.0
    associative_cue_weight: float = 1.5
    importance_cue_bonus: float = 2.5
    association_verified_status_bonus: float = 1.25
    association_boost_cap: float = 8.0
    association_boost_weight: float = 2.5
    life_wide_timeline_boost: float = 4.0
    project_timeline_evidence_boost: float = 2.0
    cognitive_map_boost_cap: float = 12.0
    cognitive_map_confidence_weight: float = 7.0
    cognitive_map_score_weight: float = 0.35
    cross_project_tie_absolute_margin: float = 6.0
    cross_project_tie_relative_margin: float = 0.15

    @classmethod
    def from_env(cls) -> "PromptRecallGatePolicy":
        return cls(scent_probe_limit=_env_int("AIPPOCAMPUS_PROMPT_PROBE_LIMIT", 8))

    def cross_project_tie_margin(self, lower_score: float) -> float:
        return max(
            self.cross_project_tie_absolute_margin,
            lower_score * self.cross_project_tie_relative_margin,
        )


@dataclass(frozen=True)
class PromptEvidencePolicy:
    candidate_scan_limit: int = 3
    hit_scan_multiplier: int = 4
    min_hit_scan: int = 4
    clean_source_high_confidence_score: float = 50.0
    clean_source_quality_bonus: float = 20.0
    final_answer_quality_bonus: float = 80.0
    user_quality_bonus: float = 35.0
    process_noise_penalty: float = 1000.0


PROMPT_RECALL_GATE_POLICY = PromptRecallGatePolicy.from_env()
PROMPT_EVIDENCE_POLICY = PromptEvidencePolicy()
