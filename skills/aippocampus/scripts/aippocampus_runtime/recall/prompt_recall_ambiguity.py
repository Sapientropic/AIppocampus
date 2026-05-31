#!/usr/bin/env python3
"""Ambiguity guards for foreground prompt-recall evidence decisions."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.recall.prompt_cues import semantic_gate_can_request_evidence
from registry import unique_preserve

_VAGUE_CROSS_PROJECT_REFERENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(上次|之前|前面|刚才|我们讨论).{0,18}(那个|这个|那条|这条).{0,10}(方案|问题|事情|东西|路线|方向|设计|结论).{0,18}(怎么说|是什么|哪句|说法|结论|决定)",
        r"(last time|previously|earlier).{0,32}(that|the).{0,16}(plan|approach|thing|idea|solution|decision|direction).{0,24}(said|wording|quote|decision|conclusion)",
        r"(как|что).{0,24}(прошлый раз|раньше|ранее|до этого|мы обсуждали).{0,32}(тот|этот|та|эта|то|это).{0,16}(план|решени[ея]|подход|иде[яю]|направлени[ея]|вывод|вариант)",
        r"(прошлый раз|раньше|ранее|до этого|мы обсуждали).{0,32}(тот|этот|та|эта|то|это).{0,16}(план|решени[ея]|подход|иде[яю]|направлени[ея]|вывод|вариант).{0,32}(как|что|опис|говор|звуч|формулиров)",
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
    natural_evidence: list[str] | None = None,
    semantic_result: dict[str, Any] | None,
) -> bool:
    has_semantic_evidence = semantic_gate_can_request_evidence(prompt, semantic_result)
    has_natural_evidence = bool(natural_evidence)
    has_source_evidence = bool(source_evidence)
    if explicit and not (has_natural_evidence or has_source_evidence or has_semantic_evidence):
        return False
    if not (has_natural_evidence or has_source_evidence or has_semantic_evidence):
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
    if has_semantic_evidence and not (explicit or has_source_evidence):
        # A semantic model can recognize vague recall intent, but without a
        # named source anchor the clean-source snippet selection is still a
        # guess. Keep the old semantic-only guard even when only one local
        # candidate survives deterministic ranking.
        return True
    strong = [
        candidate
        for candidate in candidates[:3]
        if float(candidate.get("score") or 0.0) > 0.0
    ]
    if len(strong) < 2:
        return False
    thread_keys = unique_preserve(
        [
            str(candidate.get("thread_key") or "")
            for candidate in strong
            if candidate.get("thread_key")
        ],
        limit=4,
    )
    if len(labels) < 2 and len(thread_keys) < 2:
        return False
    # Semantic and natural phrasing can both identify "this is recall", but a
    # vague "that plan/that decision" prompt still lacks a stable source anchor.
    # Keep it as scent when multiple plausible threads compete, rather than
    # turning the current or wrong thread into source-backed evidence.
    return True
