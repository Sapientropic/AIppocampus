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
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, now_utc
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

JOB_SPECS: dict[str, dict[str, Any]] = {
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
    if job in {"decision_evolution", "project_drift", "preference_candidates", "contradiction_scan"}:
        actionability += 0.12
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
                }
            ],
        },
    }
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
        if not finding["title"]:
            if job == "concept_edges":
                finding["title"] = f"{finding.get('src')} -> {finding.get('dst')}"
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
) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
    state = AgentState(source_bank=source_bank_from_turns(turns))
    step_budget = effective_step_budget(max_steps)
    batch_id = f"subconscious-job-{job}-{int(time.time())}"
    initial_payload = jobs_initial_payload(job, objective, turns, step_budget, min_tool_steps)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "job": job,
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
        response = chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_action(response)
        transcript.append({"step": step + 1, "action": action})
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
        response = chat_fn(repair_messages, api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        repair_action = parse_action(response)
        final_attempts.append(repair_action)
        if repair_action.get("action") == "final":
            findings = validate_findings(job, repair_action, state.source_bank)

    edge_count = 0
    if not no_write:
        append_job_findings(jobs_output_path, findings, model=model, batch_id=batch_id, usage=usage_total)
        edges = concept_findings_to_edges(findings)
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
        "model": model,
        "turn_count": len(turns),
        "finding_count": len(findings),
        "edge_count": edge_count if not no_write else len(concept_findings_to_edges(findings)),
        "findings": findings,
        "tool_steps": [item for item in transcript if (item.get("action") or {}).get("action") == "tool"],
        "final_attempts": final_attempts,
        "usage": usage_total,
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write else True,
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
) -> dict[str, Any]:
    results = []
    usage_total: dict[str, Any] = {}
    for job in jobs:
        result = run_one_job(
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
            dry_run=dry_run,
            no_write=no_write,
        )
        results.append(result)
        add_usage(usage_total, result.get("usage") or {})
    return {
        "ok": True,
        "jobs": results,
        "job_count": len(results),
        "finding_count": sum(int(result.get("finding_count") or 0) for result in results),
        "edge_count": sum(int(result.get("edge_count") or 0) for result in results),
        "usage": usage_total,
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write else True,
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    timeline_path = Path(args.timeline).resolve() if args.timeline else default_project_timeline_path(registry_path=registry_path)
    concept_graph_path = Path(args.concept_graph).resolve() if args.concept_graph else default_concept_graph_path(registry_path=registry_path)
    jobs_output_path = Path(args.jobs_output).resolve() if args.jobs_output else default_jobs_output_path(registry_path=registry_path)
    edges_output_path = Path(args.edges_output).resolve() if args.edges_output else default_staging_path(registry_path=registry_path)
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
        dry_run=args.dry_run,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"jobs: {result['job_count']}")
        print(f"findings: {result['finding_count']}")
        print(f"concept edges: {result['edge_count']}")
        print(f"jobs output: {result['jobs_output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
