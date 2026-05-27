#!/usr/bin/env python3
"""Job circuit catalog for AIppocampus subconscious consolidation.

This module is the authority for job definitions and the model-facing initial
payload. Keep scheduling, provider calls, validation, and staging writes in
`subconscious_jobs.py`; adding or revising a job circuit should not require
touching the execution loop.
"""

from __future__ import annotations

import json
from typing import Any

from aippocampuslib import sanitize_external_model_payload


PROMPT_VERSION = "aippocampus-subconscious-jobs-v2"

JOB_SPECS: dict[str, dict[str, Any]] = {
    "question_extraction": {
        "purpose": "Extract genuine user questions plus explicit unresolved frontier markers from source-backed turns.",
        "finding_kind": "question_candidate",
        "finding_kinds": ["question_candidate", "frontier_marker"],
        "must_include": ["title", "summary", "confidence", "source_refs", "question_text or frontier_type"],
        "notes": (
            "Use question_candidate for a real question the user was pursuing, not every interrogative sentence. "
            "Use frontier_marker only when the source explicitly shows a stopping point, unresolved boundary, missing evidence, "
            "scope boundary, or dissatisfaction. Include intent_orientation, what_features, where_context, phase_context, "
            "and collaboration_context when available. Keep question_text short and normalized; do not paste a long "
            "monologue into the question field. Use question_short as the stable label when the source wording is long."
        ),
    },
    "concept_edges": {
        "purpose": "Propose source-backed concept graph edges for ambient recall.",
        "finding_kind": "concept_edge",
        "must_include": ["src", "dst", "edge_type", "confidence", "source_refs"],
        "notes": "Use concrete concepts only. These findings can also be staged into subconscious_edges.jsonl.",
    },
    "decision_evolution": {
        "purpose": "Find decisions that changed, narrowed, superseded, or stabilized across turns/threads.",
        "finding_kind": "decision_evolution",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Describe evolution as a timeline or narrowing, not as a contradiction unless the sources truly conflict.",
    },
    "trigger_mining": {
        "purpose": "Mine ambient recall trigger candidates and query aliases.",
        "finding_kind": "trigger_candidate",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Avoid trivial utterances, Goal/system injection, and broad personalizing triggers.",
    },
    "cognitive_map": {
        "purpose": "Propose source-backed mental-map landmarks, regions, and routes for ambient recall navigation.",
        "finding_kind": "cognitive_map_route",
        "must_include": ["title", "summary", "confidence", "source_refs", "landmarks", "regions", "route_cues", "target_thread_keys"],
        "notes": (
            "Think like a hippocampal cognitive map: landmarks are durable concepts, regions are decision/topic spaces, "
            "route_cues are prompts that should navigate to those sources, and negative_cues describe contexts that should not trigger the route. "
            "Do not invent facts; every target_thread_key must be backed by source_refs."
        ),
    },
    "semantic_scope_labeling": {
        "purpose": (
            "Label fuzzy life-wide or casual-important clean-source messages with canonical scope labels. "
            "This is the DeepSeek/subconscious path for semantic judgments that must not be hard-coded into the deterministic lexical rules."
        ),
        "finding_kind": "semantic_scope_labels",
        "must_include": ["message_id", "scope_labels", "label_evidence", "summary", "confidence", "source_refs"],
        "notes": (
            "Use only canonical scope_labels from the provided list. Prefer labels for fuzzy personal reflection, idea evolution, "
            "relationship continuity, and unresolved questions. Treat personal_reflection, relationship_continuity, "
            "idea_seed, technical_work, life_context, open_question, reading_notes, and "
            "preference as fragile labels: only use personal_reflection when the user is reflecting on self, feelings, doubts, "
            "identity, or meaning, not merely mentioning an idea; only use relationship_continuity when the message explicitly "
            "depends on prior conversations, shared history, an ongoing relationship arc, or a desire for continuity with the "
            "assistant, not merely because the user asks the assistant a question or discusses memory, time, or transmission; "
            "only use idea_seed when the source itself contains a "
            "new direction, metaphor, possibility, or spark to revisit, not just a positive reaction; only use technical_work "
            "when the message itself concerns implementation, repo work, tools, architecture, tests, or technical decisions, not "
            "because adjacent project context is technical; only use life_context for concrete lived circumstance, body, "
            "schedule, mood, or day-to-day situation; only use open_question for an explicit unresolved question, uncertainty, "
            "deferred answer, or inquiry the user is still pursuing later, not an ordinary immediate question to the assistant "
            "and not merely a reflective or philosophical statement; only use reading_notes when the source explicitly reacts "
            "to or records reading material such as books, articles, papers, essays, or notes, not film or general media unless "
            "the source frames it as reading; only use preference when the user expresses a stable or situational way something should be done, "
            "not merely a one-off instruction. Do not label a message only because a keyword matched. Include label_evidence with "
            "one short source-grounded reason and confidence for every scope_label you apply; the reason must stay close to "
            "what the source message actually says and must not import neighboring project context or inferred downstream uses. "
            "Omit any label that you cannot defend with its own evidence. Each finding must target one "
            "message_id from a source_ref. These findings are navigation hints that later materialize into semantic-scope-labels.jsonl; "
            "they are not source truth."
        ),
    },
    "memory_dedup": {
        "purpose": "Identify duplicate or near-duplicate memory material across registered clean sources.",
        "finding_kind": "dedup_candidate",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Prefer canonicalization hints and merge candidates; do not delete anything.",
    },
    "project_drift": {
        "purpose": "Detect project direction shifts, phase changes, and scope drift.",
        "finding_kind": "project_drift",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Focus on durable shifts that affect future recall, planning, or product interpretation.",
    },
    "preference_candidates": {
        "purpose": "Find stable user preference candidates suitable for later formal-memory review.",
        "finding_kind": "preference_candidate",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Do not write formal preferences. Prefer multi-evidence candidates and include when-not-to-apply.",
    },
    "contradiction_scan": {
        "purpose": "Find tensions, possible contradictions, or decision conflicts that need review.",
        "finding_kind": "contradiction_candidate",
        "must_include": ["title", "summary", "confidence", "source_refs"],
        "notes": "Use 'tension' for evolving decisions; reserve contradiction for genuinely incompatible claims.",
    },
}


def job_names(value: str) -> list[str]:
    if value == "all":
        return list(JOB_SPECS)
    if value not in JOB_SPECS:
        raise ValueError(f"unknown job {value!r}; expected one of: {', '.join(JOB_SPECS)}")
    return [value]


def jobs_initial_payload(job: str, objective: str, turns: list[dict[str, Any]], max_steps: int, min_tool_steps: int) -> str:
    spec = JOB_SPECS[job]
    # DeepSeek caches exact completed prefixes. Put the stable circuit contract
    # before source turns so different source batches can still reuse the
    # schema/tool/job prefix; keep the variable objective after turns so repeated
    # samples over the same source can reuse both the static contract and source.
    # Do not sort these keys alphabetically: their order is part of the runtime
    # cache contract.
    payload = {
        "prompt_version": PROMPT_VERSION,
        "job": job,
        "job_spec": spec,
        "available_tools": {
            "search_clean_source": {"args": {"terms": ["..."], "limit": 8}},
            "get_turn_context": {"args": {"ref": "t0", "limit": 8}},
            "expand_concepts": {"args": {"terms": ["..."], "depth": 2, "limit": 16}},
            "recent_edges": {"args": {"terms": ["..."], "limit": 10}},
        },
        "final_schema": {
            "action": "final",
            "findings": [
                {
                    "kind": spec["finding_kind"],
                    "title": "short title",
                    "summary": "short source-backed finding",
                    "confidence": 0.0,
                    "source_refs": [{"ref": "t0"}],
                    "concepts": ["optional short concepts"],
                    "recommendation": "optional next action",
                    "src": "required for concept_edges only",
                    "dst": "required for concept_edges only",
                    "edge_type": "required for concept_edges only",
                    "landmarks": "required for cognitive_map only; list of durable concepts/places",
                    "regions": "required for cognitive_map only; list of topic/decision spaces",
                    "route_cues": "required for cognitive_map only; prompts or semantic cues that should navigate here",
                    "negative_cues": "optional for cognitive_map; contexts that should not trigger this route",
                    "target_thread_keys": "required for cognitive_map only; must be backed by source_refs",
                    "route_kind": "optional for cognitive_map: association|preplay|detour|blocked_route",
                    "message_id": "required for semantic_scope_labeling only; clean-source message_id being labeled",
                    "scope_labels": "required for semantic_scope_labeling only; canonical labels such as personal_reflection or idea_seed",
                    "label_evidence": (
                        "required for semantic_scope_labeling; one entry for every label in scope_labels: "
                        "{\"label\":\"canonical label\", "
                        "\"reason\":\"short source-grounded reason\", \"confidence\":0.0}"
                    ),
                    "question_text": "required for question_candidate only; exact or lightly normalized user question",
                    "question_short": "optional for question_candidate; stable short label",
                    "intent_orientation": "optional for question_candidate; angle of approach such as debugging, architecture, philosophy, writing",
                    "what_features": "optional for question_candidate; content features independent of where it appeared",
                    "where_context": "optional for question_candidate; thread/project/source context",
                    "phase_context": "optional for question_candidate; work stage such as new-project start, post-compaction, pre-closeout",
                    "collaboration_context": "optional for question_candidate; agent/profile/collaborator context when source-backed",
                    "frontier_type": "required for frontier_marker only: unresolved|blocked|deferred|unsatisfied|needs_external_evidence|scope_boundary",
                    "boundary_reason": "required for frontier_marker only; why this is a stopping point, not merely a question",
                    "linked_question_short": "optional for frontier_marker; short label of related question",
                }
            ],
        },
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "initial_turns": turns,
        "objective": objective or spec["purpose"],
    }
    payload = sanitize_external_model_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)
