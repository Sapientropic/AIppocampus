"""Prompt-shape eligibility for foreground dream delivery."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.recall.prompt_cues import prompt_is_code_surface

EXPLICIT_DREAM_RE = re.compile(
    r"(梦|dream|dream hypothesis|dream delivery|dream worker|梦的角度)",
    re.IGNORECASE,
)
LIFE_REFLECTION_RE = re.compile(
    r"(continuity|life[-_ ]?wide|reflection|journey|frontier|卡住|下一步|最近|延续|连续性)",
    re.IGNORECASE,
)


def classify_dream_delivery_task(prompt: str) -> dict[str, Any]:
    """Classify foreground dream eligibility without returning prompt text."""

    text = str(prompt or "")
    if prompt_is_code_surface(text):
        return {
            "eligible": False,
            "task_mode": "coding_current_repo",
            "reason": "ineligible_task_mode",
        }
    if EXPLICIT_DREAM_RE.search(text):
        return {
            "eligible": True,
            "task_mode": "explicit_dream",
            "reason": "eligible_task_mode",
        }
    if LIFE_REFLECTION_RE.search(text):
        return {
            "eligible": True,
            "task_mode": "life_wide_reflection",
            "reason": "eligible_task_mode",
        }
    return {
        "eligible": True,
        "task_mode": "ambient_candidate",
        "reason": "eligible_task_mode",
    }
