"""Controlled agent-native surface intent labels for the prompt hook."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.aippo import working_contract as aippo

AIppo_RE = re.compile(r"\bai\s*ppo\b|aippo|working\s+contract|工作契约|工作合同", re.IGNORECASE)
AVATAR_RE = re.compile(r"\bavatar\b|头像|化身", re.IGNORECASE)
EPISODE_ARC_RE = re.compile(r"episode[-\s]*arc|episode\s*/\s*arc|情节弧|事件弧", re.IGNORECASE)
PROJECT_EXPERIENCE_RE = re.compile(r"project\s+experience|项目经验|以前是不是反复|不要重复踩坑", re.IGNORECASE)
ARCHITECTURE_NAVIGATION_RE = re.compile(
    r"attention[-_\s]*router|topology|macro\s+orientation|sheaf|local[-_\s]*global|架构|拓扑|胶合",
    re.IGNORECASE,
)


def classify_agent_surface_intent(prompt: str) -> dict[str, Any]:
    """Return public-safe labels for explicitly requested agent-native surfaces.

    This helper deliberately emits only controlled labels and counts. The
    prompt hook may use the labels to pick an agent-native affordance, but it
    must not foreground raw prompt text or treat the labels as source evidence.
    """

    text = str(prompt or "")
    surfaces: list[str] = []
    if AIppo_RE.search(text):
        surfaces.append("aippo_working_contract")
    if AVATAR_RE.search(text):
        surfaces.append("avatar_posture")
    if EPISODE_ARC_RE.search(text):
        surfaces.append("episode_arc")
    if PROJECT_EXPERIENCE_RE.search(text):
        surfaces.append("project_experience")
    if ARCHITECTURE_NAVIGATION_RE.search(text):
        surfaces.append("architecture_navigation")

    if not surfaces:
        return {
            "explicit": False,
            "surfaces": [],
            "aippo_status": "not_requested",
            "task_families": [],
            "reason_codes": [],
        }

    task_families: list[str] = []
    aippo_status = "not_requested"
    if "aippo_working_contract" in surfaces:
        activation = aippo.activation_packet_from_working_contract(
            aippo.build_project_workflow_public_safe_contract(),
            task=text,
        )
        task_families = [
            str(item)
            for item in activation.get("task_families") or []
            if str(item).strip()
        ][:4]
        aippo_status = "ok" if int(activation.get("active_clause_count") or 0) > 0 else "no_active_contract"

    return {
        "explicit": True,
        "surfaces": surfaces,
        "aippo_status": aippo_status,
        "task_families": task_families,
        "reason_codes": ["explicit_agent_native_surface_intent"],
        "claim_boundary": "surface labels are action hints, not source-backed facts",
    }


__all__ = ["classify_agent_surface_intent"]
