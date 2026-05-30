#!/usr/bin/env python3
"""Ambiguity guards for foreground prompt-recall evidence decisions."""

from __future__ import annotations

import re
from typing import Any

from prompt_cues import semantic_gate_can_request_evidence
from registry import unique_preserve

_VAGUE_CROSS_PROJECT_REFERENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(上次|之前|前面|刚才|我们讨论).{0,18}(那个|这个|那条|这条).{0,10}(方案|问题|事情|东西|路线|方向|设计|结论).{0,18}(怎么说|是什么|哪句|说法|结论|决定)",
        r"(last time|previously|earlier).{0,32}(that|the).{0,16}(plan|approach|thing|idea|solution|decision|direction).{0,24}(said|wording|quote|decision|conclusion)",
    ]
]


def explicit_evidence_request_is_ambiguous(
    prompt: str,
    candidates: list[dict[str, Any]],
    *,
    scent_threshold: float,
) -> bool:
    if len(candidates) < 2:
        return False
    strong = [
        candidate
        for candidate in candidates[:3]
        if float(candidate.get("score") or 0.0) >= scent_threshold
    ]
    if len(strong) < 2:
        return False
    labels = unique_preserve(
        [
            str(candidate.get("project_label") or "")
            for candidate in strong
            if candidate.get("project_label")
        ],
        limit=4,
    )
    if len(labels) < 2:
        return False
    prompt_low = prompt.casefold()
    if any(label and label.casefold() in prompt_low for label in labels):
        return False
    shared_terms: dict[str, set[str]] = {}
    for candidate in strong:
        label = str(candidate.get("project_label") or "")
        for term in candidate.get("matched_terms") or []:
            normalized = str(term or "").strip().casefold()
            if len(normalized) < 3:
                continue
            shared_terms.setdefault(normalized, set()).add(label)
    if not any(len(term_labels) >= 2 for term_labels in shared_terms.values()):
        return False
    scores = [float(candidate.get("score") or 0.0) for candidate in strong[:2]]
    # If two project scopes are effectively tied on the same short entity and
    # the prompt did not name a project, source evidence would be guesswork.
    # Keep the ambient hint as scent and let the foreground model ask/follow up
    # instead of surfacing the wrong source-backed snippet.
    return abs(scores[0] - scores[1]) <= max(6.0, min(scores) * 0.15)


def semantic_evidence_request_is_vague_cross_project(
    prompt: str,
    *,
    candidates: list[dict[str, Any]],
    explicit: list[str],
    source_evidence: list[str],
    semantic_result: dict[str, Any] | None,
) -> bool:
    if explicit or source_evidence:
        return False
    if not semantic_gate_can_request_evidence(prompt, semantic_result):
        return False
    if not any(pattern.search(prompt) for pattern in _VAGUE_CROSS_PROJECT_REFERENT_PATTERNS):
        return False
    prompt_low = prompt.casefold()
    labels = unique_preserve(
        [
            str(candidate.get("project_label") or "")
            for candidate in candidates[:3]
            if candidate.get("project_label")
        ],
        limit=4,
    )
    if any(label and label.casefold() in prompt_low for label in labels):
        return False
    # Semantic can help route vague "that plan" prompts to a scent, but source
    # snippets need a stable local anchor. Without a named project/entity in the
    # user wording, a high-confidence semantic evidence answer can grab the
    # current or wrong thread when an older clean-source row is the real target.
    return True
