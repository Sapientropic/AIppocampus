#!/usr/bin/env python3
"""Prompt contract for bounded model-backed dream workers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from model_client import DEEPSEEK_PREFIX_CACHE_CONTRACT

PROMPT_VERSION = "dream_worker_v1"
PROMPT_ORDER = ["stable_dream_worker_contract", "source_pack_payload", "variable_run_directive"]


def stable_worker_contract(
    candidate_kinds_by_function: Mapping[str, set[str]],
) -> dict[str, Any]:
    return {
        "prompt_part": "stable_dream_worker_contract",
        "prompt_version": PROMPT_VERSION,
        "worker": "aippocampus_bounded_model_backed_dream_worker",
        "cache_contract": DEEPSEEK_PREFIX_CACHE_CONTRACT,
        "execution_mode": "detached_background",
        "allowed_dream_functions": sorted(candidate_kinds_by_function),
        "output_schema": {
            "findings": [
                {
                    "candidate_kind": "allowed kind for the requested dream_function",
                    "title": "short non-factual hypothesis title",
                    "summary": "tentative source-backed synthesis",
                    "activation_cues": [
                        "LLM-selected semantic cues for prompts where this hypothesis should wake"
                    ],
                    "confidence": "0.0-0.86; dream workers must stay tentative",
                    "source_ref_ids": ["sr0"],
                    "bridge_claims": [
                        {"claim": "why these source handles support the bridge", "source_ref_ids": ["sr0"]}
                    ],
                }
            ]
        },
        "hard_rules": [
            "Return JSON only.",
            "Use only source_ref_ids from the source_ref_inventory.",
            "Every candidate and every bridge_claim must cite source_ref_ids.",
            "Every candidate must include activation_cues chosen by the model; these cues are the only route surface for model-backed dream hypotheses.",
            "activation_cues must describe prompt meanings where the hypothesis matters, not copy generic words from the title or summary.",
            "Do not state private or factual claims beyond the selected source pack.",
            "Do not request foreground execution, clean-source mutation, or formal memory promotion.",
        ],
    }


def variable_run_directive(
    dream_function: str,
    *,
    max_samples: int,
    candidate_kinds_by_function: Mapping[str, set[str]],
) -> dict[str, Any]:
    return {
        "prompt_part": "variable_run_directive",
        "dream_function": dream_function,
        "max_samples": max(1, int(max_samples)),
        "allowed_candidate_kinds": sorted(candidate_kinds_by_function[dream_function]),
        "source_ref_id_rule": "source_ref_ids must come from the immediately preceding source_pack_payload",
        "activation_cue_rule": (
            "Return 2-6 concrete semantic cues that should activate this hypothesis; "
            "do not use generic scaffold words, and do not make the caller infer cues from title/summary."
        ),
        "truth_boundary": "dream_synthesized_candidate_not_fact",
    }
