#!/usr/bin/env python3
"""Run AIppocampus subconscious consolidation jobs.

Jobs are the durable background cognition layer. They use the same bounded,
read-only perception loop as `subconscious_agent.py`, but write job-specific
staging findings instead of directly changing formal memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from aippocampuslib import (
    cli_error_payload,
    cli_error_payload_from_message,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    sanitize_external_model_payload,
)
from build_concept_graph import default_concept_graph_path
from registry import registry_paths
from subconscious_agent import (
    AGENT_SYSTEM_PROMPT,
    DEFAULT_MAX_STEPS,
    DEFAULT_MIN_TOOL_STEPS,
    DEFAULT_TEMPERATURE,
    AgentState,
    ChatFn,
    add_usage,
    call_chat_json,
    compact_usage,
    effective_step_budget,
    parse_action,
    run_tool,
    source_bank_from_turns,
)
from subconscious_worker import (
    ALLOWED_EDGE_TYPES,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    append_staging_edges,
    clamp_confidence,
    default_project_timeline_path,
    default_staging_path,
    load_json,
    select_timeline_turns,
)


PROMPT_VERSION = "aippocampus-subconscious-jobs-v0"
DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"
DEFAULT_CONCURRENCY = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY", "4"))
DEFAULT_SAMPLES_PER_JOB = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB", "1"))

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


def normalize_for_fingerprint(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def finding_fingerprint(finding: dict[str, Any]) -> str:
    parts = [
        normalize_for_fingerprint(str(finding.get("job") or "")),
        normalize_for_fingerprint(str(finding.get("kind") or finding.get("finding_kind") or "")),
        normalize_for_fingerprint(str(finding.get("title") or "")),
        normalize_for_fingerprint(str(finding.get("src") or "")),
        normalize_for_fingerprint(str(finding.get("dst") or "")),
        normalize_for_fingerprint(str(finding.get("edge_type") or "")),
        normalize_for_fingerprint(str(finding.get("question_text") or "")),
        normalize_for_fingerprint(str(finding.get("frontier_type") or "")),
    ]
    digest = hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"sf_{digest}"


def quality_bucket(score: float) -> str:
    if score >= 0.82:
        return "strong"
    if score >= 0.64:
        return "usable"
    if score >= 0.48:
        return "weak"
    return "noise"


def estimate_finding_quality(job: str, finding: dict[str, Any]) -> dict[str, Any]:
    refs = [ref for ref in finding.get("source_refs") or [] if isinstance(ref, dict)]
    confidence = clamp_confidence(finding.get("confidence"))
    ref_count = len(refs)
    thread_count = len({str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")})
    final_refs = sum(1 for ref in refs if ref.get("assistant_line") or ref.get("source_line") or ref.get("message_id"))
    summary_len = len(str(finding.get("summary") or finding.get("why") or ""))
    recommendation = bool(str(finding.get("recommendation") or "").strip())
    evidence_strength = min(1.0, 0.35 + ref_count * 0.16 + thread_count * 0.10 + final_refs * 0.06)
    specificity = min(1.0, 0.25 + min(summary_len, 420) / 600 + min(len(finding.get("concepts") or []), 6) * 0.04)
    actionability = 0.35 + (0.28 if recommendation else 0.0)
    if job in {"question_extraction", "decision_evolution", "project_drift", "preference_candidates", "contradiction_scan"}:
        actionability += 0.12
    if job == "cognitive_map":
        actionability += 0.10
    novelty = 0.58
    if job == "concept_edges":
        novelty += 0.08 if finding.get("src") and finding.get("dst") else -0.12
    drift_risk = 0.20
    if job in {"contradiction_scan", "preference_candidates"}:
        drift_risk += 0.20
    if confidence < 0.65:
        drift_risk += 0.15
    promotion_readiness = (
        confidence * 0.34
        + evidence_strength * 0.26
        + specificity * 0.18
        + actionability * 0.14
        + novelty * 0.08
        - drift_risk * 0.12
    )
    promotion_readiness = max(0.0, min(1.0, promotion_readiness))
    return {
        "evidence_strength": round(evidence_strength, 4),
        "specificity": round(specificity, 4),
        "novelty": round(novelty, 4),
        "actionability": round(min(1.0, actionability), 4),
        "drift_risk": round(min(1.0, drift_risk), 4),
        "promotion_readiness": round(promotion_readiness, 4),
        "bucket": quality_bucket(promotion_readiness),
        "signals": {
            "source_ref_count": ref_count,
            "source_thread_count": thread_count,
            "has_recommendation": recommendation,
        },
    }


def default_jobs_output_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME


def job_names(value: str) -> list[str]:
    if value == "all":
        return list(JOB_SPECS)
    if value not in JOB_SPECS:
        raise ValueError(f"unknown job {value!r}; expected one of: {', '.join(JOB_SPECS)}")
    return [value]


def jobs_initial_payload(job: str, objective: str, turns: list[dict[str, Any]], max_steps: int, min_tool_steps: int) -> str:
    spec = JOB_SPECS[job]
    payload = {
        "prompt_version": PROMPT_VERSION,
        "job": job,
        "job_spec": spec,
        "objective": objective or spec["purpose"],
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "initial_turns": turns,
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
    }
    payload = sanitize_external_model_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_ref_id(ref_item: Any) -> str:
    if isinstance(ref_item, str):
        return ref_item.strip()
    if isinstance(ref_item, dict):
        return str(ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or "").strip()
    return ""


def refs_for_finding(finding: dict[str, Any], source_bank: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref_item in finding.get("source_refs") or []:
        ref_id = normalize_ref_id(ref_item)
        source = source_bank.get(ref_id)
        if not source:
            continue
        refs.append(
            {
                "ref": ref_id,
                "turn_ref": source.get("turn_ref"),
                "thread_key": source.get("thread_key"),
                "title": source.get("title"),
                "project_label": source.get("project_label"),
                "turn_id": source.get("turn_id"),
                "turn_index": source.get("turn_index"),
                "user_line": source.get("user_line"),
                "assistant_line": source.get("assistant_line"),
                "source_line": source.get("source_line"),
                "message_id": source.get("message_id"),
                "timestamp": source.get("timestamp"),
            }
        )
    return refs[:5]


def response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    return str(((choices[0].get("message") or {}).get("content") or "").strip())


def parse_action_for_job(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return parse_action(response)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "action": "parse_error",
            "error": compact_text(f"{type(exc).__name__}: {exc}", 260),
            "raw_preview": compact_text(response_content(response), 1000),
        }


def compact_string_list(values: Any, *, limit: int = 12, chars: int = 90) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, list):
        source = values
    else:
        source = []
    out: list[str] = []
    for value in source:
        text = compact_text(str(value or "").strip(), chars)
        if text:
            out.append(text)
    return list(dict.fromkeys(out))[:limit]


def validate_cognitive_map_fields(item: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    landmarks = compact_string_list(item.get("landmarks") or item.get("concepts"), limit=10)
    regions = compact_string_list(item.get("regions"), limit=8)
    route_cues = compact_string_list(item.get("route_cues") or item.get("aliases"), limit=16)
    if not landmarks or not route_cues:
        return None
    ref_threads = list(dict.fromkeys(str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")))
    requested = compact_string_list(item.get("target_thread_keys"), limit=16)
    target_thread_keys = [key for key in requested if key in ref_threads] or ref_threads
    if not target_thread_keys:
        return None
    route_kind = str(item.get("route_kind") or "association").strip() or "association"
    if route_kind not in {"association", "preplay", "detour", "blocked_route"}:
        route_kind = "association"
    return {
        "landmarks": landmarks,
        "regions": regions,
        "route_cues": route_cues,
        "negative_cues": compact_string_list(item.get("negative_cues"), limit=10),
        "target_thread_keys": target_thread_keys,
        "route_kind": route_kind,
    }


ALLOWED_QUESTION_FINDING_KINDS = {"question_candidate", "frontier_marker"}
ALLOWED_FRONTIER_TYPES = {
    "unresolved",
    "blocked",
    "deferred",
    "unsatisfied",
    "needs_external_evidence",
    "scope_boundary",
}
QUESTION_TEXT_MAX_CHARS = 140


def short_question_fallback(item: dict[str, Any]) -> str:
    for key in ("question_short", "title"):
        value = compact_text(str(item.get(key) or ""), QUESTION_TEXT_MAX_CHARS)
        if value:
            return value
    return ""


def validate_question_fields(item: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(item.get("kind") or "").strip()
    if kind not in ALLOWED_QUESTION_FINDING_KINDS:
        kind = "question_candidate"
    if kind == "question_candidate":
        raw_question_text = str(item.get("question_text") or item.get("question") or "").strip()
        question_text = compact_text(raw_question_text, QUESTION_TEXT_MAX_CHARS)
        question_text_compressed = False
        if len(raw_question_text) > QUESTION_TEXT_MAX_CHARS:
            fallback = short_question_fallback(item)
            if not fallback:
                return None
            question_text = fallback
            question_text_compressed = True
        if not question_text:
            return None
        return {
            "kind": kind,
            "question_text": question_text,
            "question_text_compressed": question_text_compressed,
            "question_short": compact_text(str(item.get("question_short") or item.get("title") or ""), 90),
            "intent_orientation": compact_text(str(item.get("intent_orientation") or ""), 80),
            "what_features": compact_string_list(item.get("what_features") or item.get("concepts"), limit=10),
            "where_context": compact_string_list(item.get("where_context"), limit=8),
            "phase_context": compact_text(str(item.get("phase_context") or ""), 80),
            "collaboration_context": compact_string_list(item.get("collaboration_context"), limit=8),
        }

    frontier_type = str(item.get("frontier_type") or "unresolved").strip()
    if frontier_type not in ALLOWED_FRONTIER_TYPES:
        frontier_type = "unresolved"
    boundary_reason = compact_text(str(item.get("boundary_reason") or item.get("summary") or ""), 260)
    if not boundary_reason:
        return None
    return {
        "kind": kind,
        "frontier_type": frontier_type,
        "boundary_reason": boundary_reason,
        "linked_question_short": compact_text(str(item.get("linked_question_short") or item.get("question_short") or ""), 90),
        "intent_orientation": compact_text(str(item.get("intent_orientation") or ""), 80),
        "where_context": compact_string_list(item.get("where_context"), limit=8),
        "phase_context": compact_text(str(item.get("phase_context") or ""), 80),
        "collaboration_context": compact_string_list(item.get("collaboration_context"), limit=8),
    }


def validate_findings(job: str, parsed: dict[str, Any], source_bank: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    spec = JOB_SPECS[job]
    out: list[dict[str, Any]] = []
    for item in parsed.get("findings") or []:
        if not isinstance(item, dict):
            continue
        confidence = clamp_confidence(item.get("confidence"))
        refs = refs_for_finding(item, source_bank)
        if confidence < 0.45 or not refs:
            continue
        finding = {
            "job": job,
            "kind": str(item.get("kind") or spec["finding_kind"]),
            "title": compact_text(str(item.get("title") or ""), 140),
            "summary": compact_text(str(item.get("summary") or item.get("why") or ""), 480),
            "confidence": round(confidence, 4),
            "source_refs": refs,
            "concepts": [compact_text(str(value), 80) for value in item.get("concepts") or [] if str(value).strip()][:12],
            "recommendation": compact_text(str(item.get("recommendation") or item.get("suggested_next_action") or ""), 260),
        }
        if job == "concept_edges":
            src = compact_text(str(item.get("src") or ""), 100)
            dst = compact_text(str(item.get("dst") or ""), 100)
            edge_type = str(item.get("edge_type") or "related")
            if not src or not dst or src.casefold() == dst.casefold():
                continue
            if edge_type not in ALLOWED_EDGE_TYPES:
                edge_type = "related"
            finding.update(
                {
                    "src": src,
                    "dst": dst,
                    "edge_type": edge_type,
                    "why": compact_text(str(item.get("why") or item.get("summary") or ""), 220),
                }
            )
        if job == "question_extraction":
            question_fields = validate_question_fields(item)
            if not question_fields:
                continue
            finding.update(question_fields)
        if job == "cognitive_map":
            route_fields = validate_cognitive_map_fields(item, refs)
            if not route_fields:
                continue
            finding.update(route_fields)
        if not finding["title"]:
            if job == "concept_edges":
                finding["title"] = f"{finding.get('src')} -> {finding.get('dst')}"
            elif job == "question_extraction" and finding.get("question_short"):
                finding["title"] = finding["question_short"]
            elif job == "cognitive_map":
                finding["title"] = " -> ".join(finding.get("landmarks") or [])[:120]
            else:
                finding["title"] = compact_text(finding["summary"], 120)
        if not finding["summary"] and job != "concept_edges":
            continue
        finding["fingerprint"] = finding_fingerprint(finding)
        finding["quality"] = estimate_finding_quality(job, finding)
        out.append(finding)
    return out


def append_job_findings(path: Path, findings: list[dict[str, Any]], *, model: str, batch_id: str, usage: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for finding in findings:
            payload = dict(finding)
            payload["finding_kind"] = payload.pop("kind", "")
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_job_finding",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": "deepseek_subconscious_jobs",
                "usage": usage or {},
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def concept_findings_to_edges(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("job") != "concept_edges":
            continue
        edges.append(
            {
                "src": finding.get("src"),
                "dst": finding.get("dst"),
                "edge_type": finding.get("edge_type") or "related",
                "confidence": finding.get("confidence"),
                "why": finding.get("why") or finding.get("summary") or finding.get("title"),
                "source_refs": finding.get("source_refs") or [],
            }
        )
    return edges


def run_one_job(
    *,
    job: str,
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    project: str | None,
    objective: str,
    max_turns: int,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    chat_fn: ChatFn = call_chat_json,
    dry_run: bool = False,
    no_write: bool = False,
    defer_writes: bool = False,
    sample_index: int = 1,
    sample_count: int = 1,
) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
    state = AgentState(source_bank=source_bank_from_turns(turns))
    step_budget = effective_step_budget(max_steps)
    batch_id = f"subconscious-job-{job}-{time.time_ns()}-{os.getpid()}-{sample_index}"
    sample_objective = objective
    if sample_count > 1:
        sample_objective = (
            f"{objective}\n\nDiversity sample {sample_index}/{sample_count}: "
            "use a distinct angle, search path, or cue framing while staying source-backed."
        ).strip()
    initial_payload = jobs_initial_payload(job, sample_objective, turns, step_budget, min_tool_steps)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "job": job,
            "sample_index": sample_index,
            "sample_count": sample_count,
            "turn_count": len(turns),
            "effective_step_budget": step_budget,
            "prompt_preview": compact_text(initial_payload, 2600),
        }
    if not api_key:
        raise RuntimeError("missing DeepSeek API key; set DEEPSEEK_API_KEY or pass --api-key-env")

    system_prompt = (
        AGENT_SYSTEM_PROMPT
        + "\nFor subconscious jobs, final answers must use `findings`, not `edges`, unless the job spec says otherwise."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_payload},
    ]
    transcript: list[dict[str, Any]] = []
    final_attempts: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    tool_count = 0
    for step in range(step_budget):
        response = chat_fn(sanitize_external_model_payload(messages), api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_action_for_job(response)
        transcript.append({"step": step + 1, "action": action})
        if action.get("action") == "parse_error":
            if step + 1 < step_budget:
                messages.append({"role": "assistant", "content": action.get("raw_preview") or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "error": "Previous response was not valid JSON.",
                                "details": action.get("error"),
                                "instruction": "Return exactly one JSON object with action=tool or action=final. Do not wrap it in Markdown.",
                                "available_refs": list(state.source_bank.keys())[:32],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                continue
            break
        if action.get("action") == "final":
            final_attempts.append(action)
            if tool_count < max(0, int(min_tool_steps)) and step + 1 < step_budget:
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append({"role": "user", "content": json.dumps({"error": "Call at least one read-only tool before finalizing."}, ensure_ascii=False)})
                continue
            candidate_findings = validate_findings(job, action, state.source_bank)
            if not candidate_findings and step + 1 < step_budget:
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "error": "No valid source-backed findings survived validation.",
                                "instruction": "Use refs from available_refs. Return action=final with findings, or empty findings only when no durable finding exists.",
                                "available_refs": list(state.source_bank.keys())[:32],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                continue
            findings = candidate_findings
            break
        if action.get("action") != "tool":
            messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
            messages.append({"role": "user", "content": json.dumps({"error": "Return action=tool or action=final only."}, ensure_ascii=False)})
            continue
        tool_name = str(action.get("tool") or "")
        tool_args = action.get("args") if isinstance(action.get("args"), dict) else {}
        observation = run_tool(
            tool_name,
            tool_args,
            registry_path=registry_path,
            project=project,
            concept_graph_path=concept_graph_path,
            staging_path=edges_output_path,
            state=state,
        )
        tool_count += 1
        transcript[-1]["observation"] = observation
        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": (
                    "TOOL_RESULT:" + "\n"
                    + json.dumps(observation, ensure_ascii=False, indent=2)
                    + "\n\nNext: call another tool if needed; otherwise return action=final with source-backed findings. "
                    "Do not return empty findings when observations contain useful durable structure."
                ),
            }
        )

    if not findings and tool_count > 0:
        repair_messages = messages + [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "repair": "final_only",
                        "instruction": "Use existing tool observations and available refs to produce source-backed findings. Do not call tools. Return action=final.",
                        "available_refs": list(state.source_bank.keys())[:40],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        response = chat_fn(sanitize_external_model_payload(repair_messages), api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        repair_action = parse_action_for_job(response)
        final_attempts.append(repair_action)
        if repair_action.get("action") == "final":
            findings = validate_findings(job, repair_action, state.source_bank)

    edges = concept_findings_to_edges(findings)
    edge_count = 0
    if not no_write and not defer_writes:
        append_job_findings(jobs_output_path, findings, model=model, batch_id=batch_id, usage=usage_total)
        if edges:
            append_staging_edges(
                edges_output_path,
                edges,
                model=model,
                batch_id=batch_id,
                usage=usage_total,
                prompt_version=PROMPT_VERSION,
                source="deepseek_subconscious_jobs",
            )
            edge_count = len(edges)
    return {
        "ok": True,
        "dry_run": False,
        "job": job,
        "sample_index": sample_index,
        "sample_count": sample_count,
        "model": model,
        "turn_count": len(turns),
        "finding_count": len(findings),
        "edge_count": edge_count if (not no_write and not defer_writes) else len(edges),
        "findings": findings,
        "tool_steps": [item for item in transcript if (item.get("action") or {}).get("action") == "tool"],
        "final_attempts": final_attempts,
        "usage": usage_total,
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write or defer_writes else True,
        "deferred_write": bool(defer_writes and not no_write),
        "batch_id": batch_id,
        "effective_step_budget": step_budget,
        "temperature": temperature,
    }


def run_jobs(
    *,
    jobs: list[str],
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    project: str | None,
    objective: str,
    max_turns: int,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    dry_run: bool = False,
    no_write: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    samples_per_job: int = DEFAULT_SAMPLES_PER_JOB,
    chat_fn: ChatFn = call_chat_json,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    task_specs = [
        (task_index, job, sample_index)
        for task_index, (job, sample_index) in enumerate(
            (job, sample_index)
            for job in jobs
            for sample_index in range(1, max(1, int(samples_per_job)) + 1)
        )
    ]

    def failed_result(job: str, sample_index: int, exc: BaseException) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": False,
            "job": job,
            "sample_index": sample_index,
            "sample_count": max(1, int(samples_per_job)),
            "model": model,
            "finding_count": 0,
            "edge_count": 0,
            "findings": [],
            "tool_steps": [],
            "final_attempts": [],
            "usage": {},
            "jobs_output": str(jobs_output_path),
            "edges_output": str(edges_output_path),
            "wrote": False,
            "deferred_write": False,
            "error": compact_text(f"{type(exc).__name__}: {exc}", 500),
        }

    def run_task(job: str, sample_index: int) -> dict[str, Any]:
        return run_one_job(
            job=job,
            registry_path=registry_path,
            timeline_path=timeline_path,
            concept_graph_path=concept_graph_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            project=project,
            objective=objective,
            max_turns=max_turns,
            max_steps=max_steps,
            min_tool_steps=min_tool_steps,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
            chat_fn=chat_fn,
            dry_run=dry_run,
            no_write=no_write,
            defer_writes=not no_write,
            sample_index=sample_index,
            sample_count=max(1, int(samples_per_job)),
        )

    max_workers = max(1, min(int(concurrency or 1), len(task_specs) or 1))
    indexed_results: list[tuple[int, dict[str, Any]]] = []
    if max_workers == 1:
        for task_index, job, sample_index in task_specs:
            try:
                indexed_results.append((task_index, run_task(job, sample_index)))
            except Exception as exc:
                indexed_results.append((task_index, failed_result(job, sample_index, exc)))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_task, job, sample_index): (task_index, job, sample_index)
                for task_index, job, sample_index in task_specs
            }
            for future in as_completed(futures):
                task_index, job, sample_index = futures[future]
                try:
                    indexed_results.append((task_index, future.result()))
                except Exception as exc:
                    indexed_results.append((task_index, failed_result(job, sample_index, exc)))
    indexed_results.sort(key=lambda item: item[0])
    results = [result for _, result in indexed_results]

    if not no_write and not dry_run:
        # DeepSeek calls can run concurrently, but staging files are append-only
        # shared artifacts. Serialize writes here so multi-sample runs do not
        # interleave JSONL rows or edge batches under parallel workers.
        for result in results:
            if result.get("ok") is False:
                continue
            append_job_findings(
                jobs_output_path,
                result.get("findings") or [],
                model=model,
                batch_id=str(result.get("batch_id") or ""),
                usage=result.get("usage") or {},
            )
            edges = concept_findings_to_edges(result.get("findings") or [])
            if edges:
                append_staging_edges(
                    edges_output_path,
                    edges,
                    model=model,
                    batch_id=str(result.get("batch_id") or ""),
                    usage=result.get("usage") or {},
                    prompt_version=PROMPT_VERSION,
                    source="deepseek_subconscious_jobs",
                )
            result["wrote"] = True
            result["deferred_write"] = False
    for result in results:
        add_usage(usage_total, result.get("usage") or {})
    successful_count = sum(1 for result in results if result.get("ok") is not False)
    failure_count = sum(1 for result in results if result.get("ok") is False)
    return {
        "ok": successful_count > 0 or not task_specs,
        "jobs": results,
        "job_count": len(results),
        "successful_job_count": successful_count,
        "failure_count": failure_count,
        "partial_failure": failure_count > 0 and successful_count > 0,
        "requested_job_count": len(jobs),
        "samples_per_job": max(1, int(samples_per_job)),
        "concurrency": max_workers,
        "finding_count": sum(int(result.get("finding_count") or 0) for result in results),
        "edge_count": sum(int(result.get("edge_count") or 0) for result in results),
        "usage": usage_total,
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write or dry_run else successful_count > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--timeline")
    parser.add_argument("--concept-graph")
    parser.add_argument("--jobs-output")
    parser.add_argument("--edges-output")
    parser.add_argument("--job", choices=["all", *JOB_SPECS.keys()], default="all")
    parser.add_argument("--project")
    parser.add_argument("--objective", default="")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--min-tool-steps", type=int, default=DEFAULT_MIN_TOOL_STEPS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--samples-per-job", type=int, default=DEFAULT_SAMPLES_PER_JOB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    timeline_path = Path(args.timeline).resolve() if args.timeline else default_project_timeline_path(registry_path=registry_path)
    concept_graph_path = Path(args.concept_graph).resolve() if args.concept_graph else default_concept_graph_path(registry_path=registry_path)
    jobs_output_path = Path(args.jobs_output).resolve() if args.jobs_output else default_jobs_output_path(registry_path=registry_path)
    edges_output_path = Path(args.edges_output).resolve() if args.edges_output else default_staging_path(registry_path=registry_path)
    try:
        result = run_jobs(
            jobs=job_names(args.job),
            registry_path=registry_path,
            timeline_path=timeline_path,
            concept_graph_path=concept_graph_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            project=args.project,
            objective=args.objective,
            max_turns=args.max_turns,
            max_steps=args.max_steps,
            min_tool_steps=args.min_tool_steps,
            model=args.model,
            base_url=args.base_url,
            api_key=os.environ.get(args.api_key_env),
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            temperature=args.temperature,
            concurrency=args.concurrency,
            samples_per_job=args.samples_per_job,
            dry_run=args.dry_run,
            no_write=args.no_write,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if not result.get("ok") and not result.get("error"):
        first_error = next((str(item.get("error") or "") for item in result.get("jobs") or [] if item.get("error")), "")
        if first_error:
            result["error"] = cli_error_payload_from_message(first_error)["error"]
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"jobs: {result['job_count']}")
        print(f"findings: {result['finding_count']}")
        print(f"concept edges: {result['edge_count']}")
        print(f"jobs output: {result['jobs_output']}")
    if result.get("ok"):
        return 0
    return cli_exit_code_for_error_code(str((result.get("error") or {}).get("code") or "runtime_error"))


if __name__ == "__main__":
    raise SystemExit(main())
