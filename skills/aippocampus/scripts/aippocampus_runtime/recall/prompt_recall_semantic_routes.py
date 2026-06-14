"""Semantic-route promotion guards for foreground recall."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.recall.prompt_cues import (
    semantic_gate_can_request_evidence,
    semantic_gate_can_request_source_reopen,
    semantic_gate_is_memory_cue,
)
from aippocampus_runtime.recall.prompt_recall_projection import (
    semantic_bridge_diagnostic as resolve_semantic_bridge_diagnostic,
)


def semantic_route_agrees_with_current_scope(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    semantic_result: dict[str, Any] | None,
    current_project_label: str | None,
) -> bool:
    if not candidates:
        return False
    top = candidates[0]
    label = str(top.get("project_label") or "").strip()
    current = str(current_project_label or "").strip()
    if not label or not current or label.casefold() == current.casefold():
        return True
    prompt_and_aliases = " ".join(
        [
            prompt,
            *(str(value) for value in (semantic_result or {}).get("query_aliases") or []),
            *(str(value) for value in (semantic_result or {}).get("memory_scope") or []),
        ]
    ).casefold()
    return bool(label.casefold() in prompt_and_aliases)


def semantic_source_reopen_route_ready(
    prompt: str,
    decision: str,
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    suppressed: bool,
    ambiguous_evidence_request: bool,
    semantic_result: dict[str, Any] | None,
    current_project_label: str | None,
) -> bool:
    if not semantic_route_agrees_with_current_scope(
        prompt=prompt,
        candidates=candidates,
        semantic_result=semantic_result,
        current_project_label=current_project_label,
    ):
        return False
    return bool(
        decision == "scent"
        and candidates
        and not evidence
        and not suppressed
        and not ambiguous_evidence_request
        and semantic_gate_can_request_source_reopen(prompt, semantic_result)
    )


def resolve_semantic_route_state(
    *,
    prompt: str,
    decision: str,
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    suppressed: bool,
    ambiguous_evidence_request: bool,
    semantic_result: dict[str, Any] | None,
    current_project_label: str | None,
    reasons: list[str],
) -> tuple[str, bool, str | None]:
    if decision == "skip" and not suppressed and semantic_gate_can_request_evidence(prompt, semantic_result):
        # Semantic evidence without local source stays a route hint, not evidence.
        decision = "scent"
    if decision == "skip" and not suppressed and semantic_gate_is_memory_cue(semantic_result):
        # A semantic-only cue can tell the agent where to look next, but it is
        # still not evidence until a local source route agrees and reopens.
        decision = "scent"

    source_reopen_route = semantic_source_reopen_route_ready(
        prompt,
        decision,
        candidates,
        evidence,
        suppressed,
        ambiguous_evidence_request,
        semantic_result,
        current_project_label,
    )
    bridge_diagnostic = resolve_semantic_bridge_diagnostic(
        prompt=prompt,
        semantic_result=semantic_result,
        evidence=evidence,
        source_reopen_route_ready=source_reopen_route,
        reasons=reasons,
    )
    return decision, source_reopen_route, bridge_diagnostic
