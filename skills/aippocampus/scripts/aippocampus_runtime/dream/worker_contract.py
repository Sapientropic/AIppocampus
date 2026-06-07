"""Prompt contract for bounded model-backed dream workers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.model.client import DEEPSEEK_PREFIX_CACHE_CONTRACT

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
        "worker_stance": {
            "role": "source_body_dream_worker",
            "not": [
                "auditor_only",
                "user_persona_simulator",
                "factual_claim_authority",
            ],
            "shared_body": "selected clean-source refs, route notes, texture, and source-pack context",
            "same_source_body_not_same_persistent_self": True,
            "facing": "future_foreground_agent",
            "task": (
                "Surface source-shaped possibilities that help a future agent "
                "recognize, choose, or reopen source."
            ),
            "boundary": "hypothesis_and_navigation_never_source_truth",
        },
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
                    "foreground_affordance": "optional: what this helps a future agent notice or do",
                    "source_body_shape": "optional: compact source-bounded shape of the selected source terrain",
                    "agent_position": "optional: position the future foreground agent would be facing",
                    "atmosphere_tags": ["optional direction-only tags, never facts"],
                    "waking_path": "optional: source_reopen | user_probe | retrospective_support | stay_parked",
                    "what_not_to_overclaim": "optional compact boundary in plain language",
                    "constructive_artifact": {
                        "artifact_kind": "optional: draft_question | draft_prompt | draft_outline | draft_probe",
                        "draft_text": "synthetic question, prompt, outline, or probe text",
                        "draft_origin": "compact source-shaped origin note",
                        "intended_use": "foreground_probe | source_reopen_check | planning_seed",
                        "status": "dream_draft_not_source",
                        "source_ref_ids": ["sr0"],
                        "counter_evidence": ["why this draft might not apply"],
                        "when_not_to_use": ["exact source claim"],
                    },
                    "prospective_invitation": {
                        "emerging_theme": "optional prospective theme",
                        "trigger_condition": "current prompt condition that may wake the invitation",
                        "suggested_opening": "question-first wording, not an assertion",
                        "invitation_type": "prospective_open | light_question | source_reopen_first",
                        "expires_after": "duration such as 14d",
                        "annoyance_risk": "low | medium | high",
                        "status": "dream_invitation_not_source_fact",
                        "source_ref_ids": ["sr0"],
                    },
                }
            ]
        },
        "hard_rules": [
            "Return JSON only.",
            "Use only source_ref_ids from the source_ref_inventory.",
            "Every candidate and every bridge_claim must cite source_ref_ids.",
            "Every candidate must include activation_cues chosen by the model; these cues are the only route surface for model-backed dream hypotheses.",
            "activation_cues must describe prompt meanings where the hypothesis matters, not copy generic words from the title or summary.",
            "constructive_artifact may draft useful new questions or probes, but must stay status=dream_draft_not_source with source_ref_ids, counter_evidence, and when_not_to_use.",
            "prospective_invitation may surface only as question-first optional wording under matching trigger conditions; status must be dream_invitation_not_source_fact.",
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
        "constructive_artifact_rule": (
            "For compensatory or active_imagination, optional constructive_artifact may synthesize "
            "a draft question, prompt, outline, or probe. It is allowed to be creative, but it must "
            "cite source_ref_ids, include counter_evidence and when_not_to_use, and stay "
            "dream_draft_not_source."
        ),
        "prospective_invitation_rule": (
            "For prospective only, optional prospective_invitation must include trigger_condition, "
            "question-first suggested_opening, valid invitation_type, expires_after, annoyance_risk, "
            "source_ref_ids, and status=dream_invitation_not_source_fact."
        ),
    }
