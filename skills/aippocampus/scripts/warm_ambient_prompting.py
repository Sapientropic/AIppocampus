#!/usr/bin/env python3
"""Prompt rendering for warm ambient recall scouts.

Prompt shape is a cache and behavior contract, not runtime orchestration. Keep
it separate from model execution so scout prompt tuning cannot quietly tangle
with job scheduling, source validation, or cache writes.
"""

from __future__ import annotations

import json
from typing import Any

from warm_ambient_scout_profiles import (
    FAMILY_TASKS,
    SCOUT_PRIORITY,
    VARIANT_TASKS,
    lens_task_for,
    output_profile_for_family,
    scout_lane_parts,
)

SYSTEM_PROMPT = """You are an AIppocampus warm ambient-recall scout.
Return strict JSON only. You are not memory truth and you are not answering the
user. Propose compact recall hints for deterministic local validation.

Rules:
- Do not claim facts without source refs.
- Only cite source_refs already present in the shared context; if no concrete
  source_ref is available, return an empty source_refs array.
- Do not include secrets, local file paths, API keys, cookies, or long quotes.
- Prefer small, useful signals over broad summaries.
- A source-backed card needs concrete source_refs. Otherwise use scent/candidate.
- Topic epoch is an LLM judgment: return topic_epoch_action
  "reuse|rotate|suppress", a short topic_epoch_label, and topic_epoch_reason
  when the current prompt trace suggests cache reuse or rotation.
- If the association is private, unrelated, current-thread echo, or too weak,
  return decision "skip" or "background_only".
"""

OUTPUT_BUDGET_RULES = """Output budget rules:
- Do not copy or fill output_contract/output_profile; they are schema only.
- Return one compact JSON object using only scout_task.output_profile fields.
- Omit empty arrays and unused optional fields.
- Keep reason/topic_epoch_reason under one short clause.
- If you cannot produce a field that will be used, omit it.
"""


def _shared_context_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    shared = {
        "prompt_version": payload.get("prompt_version"),
        "task": payload.get("task"),
        "workspace_name": payload.get("workspace_name"),
        "output_contract": payload.get("output_contract"),
        "memory_catalog": payload.get("memory_catalog") or [],
    }
    return {
        key: value
        for key, value in shared.items()
        if value is not None and value != "" and value != []
    }


def _prompt_context_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    context = {
        "prompt": payload.get("prompt") or "",
        "prompt_terms": payload.get("prompt_terms") or [],
    }
    if payload.get("prompt_trace"):
        context["prompt_trace"] = payload.get("prompt_trace")
    return context


def _variant_context_for_prompt(variant: str, payload: dict[str, Any]) -> dict[str, Any]:
    del payload
    if variant in {"current_trace_window", "clean_source_window", "skeptic_window"}:
        return {"prompt_trace_policy": "use prompt_context.prompt_trace for echo, source-ref, drift, and gap checks"}
    return {}


def scout_prompt(scout: str, payload: dict[str, Any]) -> str:
    family, variant = scout_lane_parts(scout)
    return json.dumps(
        {
            "output_budget": OUTPUT_BUDGET_RULES,
            # Prefix order is tuned for DeepSeek-style complete-prefix cache
            # units. Stable catalog/context comes first for cross-case reuse;
            # sanitized prompt/trace comes before the scout split so the 50
            # lanes of one case can reuse the same case prefix after the warmup
            # wave. Keep scout_task after prompt_context; moving it earlier
            # makes every lane diverge before the largest same-case prefix.
            "shared_context": _shared_context_for_prompt(payload),
            "prompt_context": _prompt_context_for_prompt(payload),
            "scout_task": {
                "scout": f"{family}:{variant}",
                "scout_family": family,
                "scout_variant": variant,
                "priority": SCOUT_PRIORITY.get(family, "P1"),
                "family_task": FAMILY_TASKS.get(family, "Analyze warm ambient recall relevance."),
                "variant_task": VARIANT_TASKS.get(variant, "Use this candidate/query variant carefully."),
                "lens_task": lens_task_for(family, variant),
                "output_profile": output_profile_for_family(family),
            },
            "variant_context": _variant_context_for_prompt(variant, payload),
        },
        ensure_ascii=False,
        indent=2,
    )
