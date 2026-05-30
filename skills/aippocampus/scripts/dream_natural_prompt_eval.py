#!/usr/bin/env python3
"""Large-sample natural-prompt eval for adjudicated dream hypotheses.

This runner tests the foreground route question that the structural dream eval
does not answer: can dream hypotheses reduce explicit "please recall this"
nudges under ordinary prompts, and do they stay quiet for unrelated or
over-personalizing prompts?

Outputs are aggregate and sanitized. Prompts are generated from selected
source-backed pack terms for the run, but the report stores only hashes and
counts, never raw prompts, source refs, thread ids, message ids, or local paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import dream_real_history_eval as dream_eval
from aippocampuslib import now_utc
from dream_working_memory import plan_dream_hypothesis_use
from memory_candidate_router import (
    DREAM_HYPOTHESIS_TYPE,
    default_jobs_path,
    default_working_memory_path,
    iter_jsonl,
    load_working_memory,
    match_working_memory,
)
from registry_store import registry_paths

SCHEMA_VERSION = 1
EVAL_KIND = "aippocampus_dream_natural_prompt_eval"
CLAIM_LEVEL = "large_sample_natural_prompt_route_eval"

DEFAULT_NATURAL_TEMPLATES = (
    "{term} 这条线下一步怎么收？",
    "{term} 现在该优先补哪块？",
    "{term} 这里还有什么没接上的边？",
    "继续 {term} 那条线。",
    "围绕 {term} 做一次反思整理。",
    "{term} 相关的旧坑别漏了。",
)
DEFAULT_MANUAL_TEMPLATES = (
    "回忆一下之前关于 {term} 的 source-backed 线索，再继续。",
    "找回我们过去讨论 {term} 的上下文。",
)
DEFAULT_STRONG_CLAIM_TEMPLATES = (
    "不用重开来源，直接说 {term} 证明了什么。",
    "把 {term} 当成我的稳定偏好来回答。",
)
DEFAULT_NEGATIVE_PROMPTS = (
    "帮我把按钮样式调顺一点。",
    "这个部署失败先看日志。",
    "写一个普通 SQL 查询。",
    "整理一下今天的会议议程。",
    "帮我回一封普通邮件。",
    "判断一下我的人格和真实偏好。",
    "不用来源，直接说我是不是一直偏好这个方向。",
    "这块没接上的边继续想。",
)


def prompt_sha1(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8", errors="replace")).hexdigest()[:16]


def ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def unique_working_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("candidate_key") or row.get("title") or row)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def non_dream_working_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE]


def pack_term(pack: Mapping[str, Any]) -> str:
    return str((pack.get("selection") or {}).get("resonance_term") or "").strip()


def prompts_for_pack(pack: Mapping[str, Any], templates: Iterable[str]) -> list[str]:
    term = pack_term(pack)
    if not term:
        return []
    return [template.format(term=term) for template in templates]


def dream_matches(prompt: str, rows: list[dict[str, Any]], *, project_label: str | None) -> list[dict[str, Any]]:
    return [
        match
        for match in match_working_memory(prompt, rows, project_label=project_label, limit=12)
        if match.get("candidate_type") == DREAM_HYPOTHESIS_TYPE
    ]


def any_route_match(prompt: str, rows: list[dict[str, Any]], *, project_label: str | None) -> bool:
    return bool(match_working_memory(prompt, rows, project_label=project_label, limit=8))


def source_finding_fanout(rows: Iterable[Mapping[str, Any]]) -> int:
    ids = {
        str(source_id)
        for row in rows
        for source_id in (row.get("source_finding_ids") or [])
        if source_id
    }
    return len(ids)


def evaluate_natural_prompts(
    *,
    packs: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    augmented_rows: list[dict[str, Any]],
    dream_rows: list[dict[str, Any]],
    project_label: str | None,
    natural_templates: Iterable[str],
    manual_templates: Iterable[str],
    overbroad_threshold: int,
) -> dict[str, Any]:
    prompt_count = 0
    baseline_hit_count = 0
    augmented_hit_count = 0
    dream_hit_count = 0
    reduction_count = 0
    overbroad_count = 0
    overbroad_examples: list[dict[str, Any]] = []
    dream_match_total = 0
    dream_fanout_total = 0

    for pack in packs:
        natural_prompts = prompts_for_pack(pack, natural_templates)
        manual_prompts = prompts_for_pack(pack, manual_templates)
        manual_would_help = any(
            any_route_match(prompt, baseline_rows, project_label=project_label)
            or any_route_match(prompt, augmented_rows, project_label=project_label)
            for prompt in manual_prompts
        )
        for prompt in natural_prompts:
            prompt_count += 1
            baseline_hit = any_route_match(prompt, baseline_rows, project_label=project_label)
            augmented_hit = any_route_match(prompt, augmented_rows, project_label=project_label)
            prompt_dream_matches = dream_matches(prompt, dream_rows, project_label=project_label)
            fanout = source_finding_fanout(prompt_dream_matches)
            dream_match_total += len(prompt_dream_matches)
            dream_fanout_total += fanout
            baseline_hit_count += int(baseline_hit)
            augmented_hit_count += int(augmented_hit)
            dream_hit_count += int(bool(prompt_dream_matches))
            if (not baseline_hit) and prompt_dream_matches and manual_would_help:
                reduction_count += 1
            if len(prompt_dream_matches) > overbroad_threshold or fanout > overbroad_threshold:
                overbroad_count += 1
                if len(overbroad_examples) < 8:
                    overbroad_examples.append(
                        {
                            "prompt_sha1": prompt_sha1(prompt),
                            "dream_match_count": len(prompt_dream_matches),
                            "source_finding_fanout": fanout,
                        }
                    )

    return {
        "natural_prompt_count": prompt_count,
        "baseline_hit_count": baseline_hit_count,
        "augmented_hit_count": augmented_hit_count,
        "dream_hit_count": dream_hit_count,
        "baseline_hit_rate": ratio(baseline_hit_count, prompt_count),
        "augmented_hit_rate": ratio(augmented_hit_count, prompt_count),
        "dream_hit_rate": ratio(dream_hit_count, prompt_count),
        "hit_rate_delta": round(
            ratio(augmented_hit_count, prompt_count) - ratio(baseline_hit_count, prompt_count),
            4,
        ),
        "manual_reminder_reduction_count": reduction_count,
        "manual_reminder_reduction_rate": ratio(reduction_count, prompt_count),
        "mean_dream_matches_per_prompt": ratio(dream_match_total, prompt_count),
        "mean_source_finding_fanout_per_prompt": ratio(dream_fanout_total, prompt_count),
        "overbroad_prompt_count": overbroad_count,
        "overbroad_examples": overbroad_examples,
    }


def evaluate_negative_prompts(
    *,
    prompts: Iterable[str],
    augmented_rows: list[dict[str, Any]],
    project_label: str | None,
) -> dict[str, Any]:
    prompt_list = list(prompts)
    dream_match_count = 0
    matched_examples: list[dict[str, Any]] = []
    for prompt in prompt_list:
        matches = dream_matches(prompt, augmented_rows, project_label=project_label)
        if matches:
            dream_match_count += 1
            if len(matched_examples) < 8:
                matched_examples.append(
                    {
                        "prompt_sha1": prompt_sha1(prompt),
                        "dream_match_count": len(matches),
                        "source_finding_fanout": source_finding_fanout(matches),
                    }
                )
    return {
        "negative_prompt_count": len(prompt_list),
        "negative_dream_match_count": dream_match_count,
        "negative_dream_match_rate": ratio(dream_match_count, len(prompt_list)),
        "matched_examples": matched_examples,
    }


def evaluate_strong_claims(
    *,
    packs: list[dict[str, Any]],
    dream_rows: list[dict[str, Any]],
    project_label: str | None,
    templates: Iterable[str],
) -> dict[str, Any]:
    prompt_count = 0
    matched_count = 0
    reopen_count = 0
    silent_count = 0
    for pack in packs:
        for prompt in prompts_for_pack(pack, templates):
            prompt_count += 1
            matches = dream_matches(prompt, dream_rows, project_label=project_label)
            if not matches:
                silent_count += 1
                continue
            matched_count += 1
            plans = [
                plan_dream_hypothesis_use(row, prompt=prompt, strong_user_facing_claim=True)
                for row in matches
            ]
            if plans and all(plan.get("action") == "reopen_source" for plan in plans):
                reopen_count += 1
    return {
        "strong_claim_prompt_count": prompt_count,
        "strong_claim_dream_match_count": matched_count,
        "strong_claim_reopen_count": reopen_count,
        "strong_claim_silent_count": silent_count,
        "strong_claim_reopen_rate": ratio(reopen_count, matched_count),
    }


def repeated_negative_prompts(repetitions: int) -> list[str]:
    return [prompt for _ in range(max(1, repetitions)) for prompt in DEFAULT_NEGATIVE_PROMPTS]


def eval_status(natural: Mapping[str, Any], noise: Mapping[str, Any]) -> str:
    if int(natural.get("natural_prompt_count") or 0) == 0:
        return "insufficient_sample"
    if int(noise.get("negative_dream_match_count") or 0) > 0:
        return "noise_risk_observed"
    if int(natural.get("manual_reminder_reduction_count") or 0) > 0:
        return "natural_prompt_lift_without_negative_noise"
    return "no_manual_reminder_reduction_observed"


def run_dream_natural_prompt_eval(
    *,
    job_rows: Iterable[Mapping[str, Any]] | None = None,
    working_memory_rows: Iterable[Mapping[str, Any]] | None = None,
    baseline_working_memory_rows: Iterable[Mapping[str, Any]] | None = None,
    registry_dir: Path | None = None,
    jobs_path: Path | None = None,
    working_memory_path: Path | None = None,
    max_packs: int = 64,
    min_packs: int = 1,
    natural_templates: Iterable[str] = DEFAULT_NATURAL_TEMPLATES,
    manual_templates: Iterable[str] = DEFAULT_MANUAL_TEMPLATES,
    strong_claim_templates: Iterable[str] = DEFAULT_STRONG_CLAIM_TEMPLATES,
    negative_repetitions: int = 20,
    overbroad_threshold: int = 4,
    project_label: str = "AIppocampus",
) -> dict[str, Any]:
    natural_template_list = tuple(natural_templates)
    manual_template_list = tuple(manual_templates)
    strong_claim_template_list = tuple(strong_claim_templates)
    registry_path, _ = registry_paths(registry_dir)
    jobs = list(job_rows) if job_rows is not None else iter_jsonl(jobs_path or default_jobs_path(registry_path))
    working_rows = (
        list(working_memory_rows)
        if working_memory_rows is not None
        else load_working_memory(working_memory_path or default_working_memory_path(registry_path))
    )
    baseline_rows = (
        [dict(row) for row in baseline_working_memory_rows]
        if baseline_working_memory_rows is not None
        else non_dream_working_rows(working_rows)
    )
    packs = dream_eval.select_real_history_packs(
        job_rows=jobs,
        working_memory_rows=working_rows,
        max_packs=max_packs,
    )
    worker_runs = [dream_eval.run_pack_dream_worker(pack) for pack in packs]
    dream_rows = [
        row
        for run in worker_runs
        for row in run.get("dream_working_memory_rows") or []
        if isinstance(row, dict)
    ]
    augmented_rows = unique_working_rows([*baseline_rows, *dream_rows])

    natural = evaluate_natural_prompts(
        packs=packs,
        baseline_rows=baseline_rows,
        augmented_rows=augmented_rows,
        dream_rows=dream_rows,
        project_label=project_label,
        natural_templates=natural_template_list,
        manual_templates=manual_template_list,
        overbroad_threshold=overbroad_threshold,
    )
    noise = evaluate_negative_prompts(
        prompts=repeated_negative_prompts(negative_repetitions),
        augmented_rows=augmented_rows,
        project_label=project_label,
    )
    strong_claims = evaluate_strong_claims(
        packs=packs,
        dream_rows=dream_rows,
        project_label=project_label,
        templates=strong_claim_template_list,
    )
    status = "insufficient_sample" if len(packs) < min_packs else eval_status(natural, noise)
    natural_prompt_count = int(natural.get("natural_prompt_count") or 0)
    negative_prompt_count = int(noise.get("negative_prompt_count") or 0)
    strong_prompt_count = int(strong_claims.get("strong_claim_prompt_count") or 0)
    can_claim = [
        "large_sample_natural_prompt_route_eval_ran",
        "negative_prompt_noise_rate_measured",
        "strong_claim_source_reopen_gate_measured",
    ]
    if int(natural.get("manual_reminder_reduction_count") or 0) > 0:
        can_claim.append("manual_reminder_reduction_observed_in_route_eval")
    if int(noise.get("negative_dream_match_count") or 0) == 0 and negative_prompt_count:
        can_claim.append("no_negative_prompt_dream_matches_observed")
    if float(strong_claims.get("strong_claim_reopen_rate") or 0.0) == 1.0:
        can_claim.append("strong_dream_claims_require_source_reopen")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVAL_KIND,
        "created_at": now_utc(),
        "status": status,
        "claim_level": CLAIM_LEVEL,
        "private_text_emitted": False,
        "metrics": {
            "sample": {
                "job_row_count": len(jobs),
                "working_memory_row_count": len(working_rows),
                "baseline_working_memory_row_count": len(baseline_rows),
                "pack_count": len(packs),
                "dream_working_memory_count": len(dream_rows),
                "natural_prompt_count": natural_prompt_count,
                "manual_prompt_count": len(packs) * len(manual_template_list),
                "negative_prompt_count": negative_prompt_count,
                "strong_claim_prompt_count": strong_prompt_count,
                "effective_prompt_count": natural_prompt_count
                + negative_prompt_count
                + strong_prompt_count,
                "min_packs": min_packs,
            },
            "manual_reminder": {
                "reduction_count": natural["manual_reminder_reduction_count"],
                "reduction_rate": natural["manual_reminder_reduction_rate"],
                "baseline_natural_hit_rate": natural["baseline_hit_rate"],
                "augmented_natural_hit_rate": natural["augmented_hit_rate"],
                "natural_hit_rate_delta": natural["hit_rate_delta"],
                "dream_natural_hit_rate": natural["dream_hit_rate"],
            },
            "natural_route": natural,
            "noise": noise,
            "strong_claims": strong_claims,
        },
        "can_claim": can_claim,
        "cannot_claim": [
            "real_user_behavior_without_live_ab_test",
            "live_model_behavioral_lift",
            "dream_hypothesis_truth_without_source_reopen",
            "full_history_coverage",
            "general_dream_quality",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run natural-prompt dream route eval.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--working-memory", type=Path)
    parser.add_argument("--max-packs", type=int, default=64)
    parser.add_argument("--min-packs", type=int, default=1)
    parser.add_argument("--negative-repetitions", type=int, default=20)
    parser.add_argument("--overbroad-threshold", type=int, default=4)
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_dream_natural_prompt_eval(
        registry_dir=args.registry_dir,
        jobs_path=args.jobs,
        working_memory_path=args.working_memory,
        max_packs=args.max_packs,
        min_packs=args.min_packs,
        negative_repetitions=args.negative_repetitions,
        overbroad_threshold=args.overbroad_threshold,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("status") != "insufficient_sample" else 1


if __name__ == "__main__":
    raise SystemExit(main())
