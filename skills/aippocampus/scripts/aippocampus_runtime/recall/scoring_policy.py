#!/usr/bin/env python3
"""Named recall scoring policies.

These values are product behavior, not formatting constants. Keep them grouped
by the recall decision they influence so future tuning reviews the source-backed
retrieval boundary instead of hunting scattered magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseWeightPolicy:
    final_answer: float = 18.0
    user: float = 3.0
    commentary: float = -5.0
    tool: float = -12.0


@dataclass(frozen=True)
class FtsRankPolicy:
    base: float
    step: float
    minimum: float = 1.0

    def score_position(self, position: int) -> float:
        return max(self.minimum, self.base - position * self.step)


@dataclass(frozen=True)
class RetrievalTextPolicy:
    literal_scan_signal: float = 15.0
    literal_hit: float = 14.0
    expanded_hit: float = 1.5
    anchor_hit: float = 2.0
    rag_chunk_multiplier: float = 0.35


@dataclass(frozen=True)
class RagChunkTextPolicy:
    literal_scan_signal: float = 12.0
    literal_hit: float = 16.0
    expanded_hit: float = 2.0
    anchor_hit: float = 3.0


@dataclass(frozen=True)
class RetrievalDiversityPolicy:
    bucket_repeat_penalty: float = 12.0
    nearby_line_window: int = 25
    nearby_line_penalty: float = 10.0
    early_literal_boost: float = 8.0
    early_line_divisor: float = 250.0


@dataclass(frozen=True)
class SegmentMergePolicy:
    # User-visible cross-segment ranking policy. Keep value changes paired with
    # the public-safe calibration fixture and report:
    # benchmarks/aippocampus/benchmark_segmented_merge_policy.py and
    # docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md.
    # Passing that fixture is diagnostic only; it is not real recall-quality
    # proof or a substitute for source-evidence retrieval benchmarks.
    final_answer_bonus: float = 12.0
    commentary_penalty: float = -4.0
    same_segment_penalty: float = 7.0
    nearby_line_window: int = 25
    nearby_line_penalty: float = 8.0
    user_literal_bonus: float = 3.0


@dataclass(frozen=True)
class ActiveRecallDecisionPolicy:
    recall_trigger_cap: float = 6.0
    recall_trigger_weight: float = 1.5
    concept_trigger_cap: float = 4.0
    concept_trigger_weight: float = 2.0
    profile_cue_bonus: float = 3.0
    life_wide_cue_bonus: float = 3.0
    anchor_overlap_cap: float = 5.0
    anchor_score_divisor: float = 4.0
    stale_index_bonus: float = 1.5
    checkpoint_due_bonus: float = 1.0
    graphify_recommendation_bonus: float = 0.5
    search_threshold: float = 3.0
    high_threshold: float = 6.0


@dataclass(frozen=True)
class SignalBlendWeights:
    text: float
    vector: float
    graph: float
    source: float

    def as_dict(self) -> dict[str, float]:
        return {
            "text": self.text,
            "vector": self.vector,
            "graph": self.graph,
            "source": self.source,
        }


@dataclass(frozen=True)
class SourceSignalPolicy:
    # Source join presence is enforced as a hard eligibility gate in
    # score_fusion.blend(). These values are only the post-gate provenance
    # richness hint, so a join key without source refs deliberately gets no
    # ranking boost.
    ref_base: float = 0.55
    per_ref: float = 0.15
    maximum: float = 1.0
    join_key_only: float = 0.0


@dataclass(frozen=True)
class ScoreFusionPolicy:
    # The source weight stays small because provenance richness is a tie-break
    # after the source-join gate, not a second evidence/authority layer.
    # The 2026-06-14 source-joined routing decision keeps vector/graph weights
    # post-join only: these weights do not enable vector prefiltering, local
    # embedding adapters, foreground model calls, or source-free semantic hits.
    # Change those defaults only with a new public replayable consumer report.
    normal_recall: SignalBlendWeights = SignalBlendWeights(
        text=0.65, vector=0.20, graph=0.10, source=0.05
    )
    exact_quote: SignalBlendWeights = SignalBlendWeights(
        text=0.84, vector=0.07, graph=0.04, source=0.05
    )
    question_tracking: SignalBlendWeights = SignalBlendWeights(
        text=0.35, vector=0.45, graph=0.15, source=0.05
    )
    theme_emergence: SignalBlendWeights = SignalBlendWeights(
        text=0.25, vector=0.20, graph=0.50, source=0.05
    )
    exact_text_guard_threshold: float = 0.85
    exact_text_guard_bonus: float = 0.08

    def context_weights_dict(self) -> dict[str, dict[str, float]]:
        return {
            "normal_recall": self.normal_recall.as_dict(),
            "exact_quote": self.exact_quote.as_dict(),
            "question_tracking": self.question_tracking.as_dict(),
            "theme_emergence": self.theme_emergence.as_dict(),
        }

    def weights_for(self, context: str) -> dict[str, float]:
        return self.context_weights_dict().get(context, self.normal_recall.as_dict())

    def canonical_context(self, context: str) -> str:
        return context if context in self.context_weights_dict() else "normal_recall"


PHASE_WEIGHT_POLICY = PhaseWeightPolicy()
MESSAGE_FTS_POLICY = FtsRankPolicy(base=80.0, step=0.5)
RAG_CHUNK_FTS_POLICY = FtsRankPolicy(base=60.0, step=0.7)
RETRIEVAL_TEXT_POLICY = RetrievalTextPolicy()
RAG_CHUNK_TEXT_POLICY = RagChunkTextPolicy()
RETRIEVAL_DIVERSITY_POLICY = RetrievalDiversityPolicy()
SEGMENT_MERGE_POLICY = SegmentMergePolicy()
ACTIVE_RECALL_POLICY = ActiveRecallDecisionPolicy()
SOURCE_SIGNAL_POLICY = SourceSignalPolicy()
SCORE_FUSION_POLICY = ScoreFusionPolicy()
