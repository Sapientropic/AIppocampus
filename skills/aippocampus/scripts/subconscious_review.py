#!/usr/bin/env python3
"""Review AIppocampus subconscious job findings for promotion candidates."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    resolve_model_route,
    route_artifact_source,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampuslib import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    sanitize_external_model_payload,
)
from registry import registry_paths, unique_preserve
from retrieval import split_query_terms
from subconscious_job_validation import (
    estimate_finding_quality,
    finding_fingerprint,
)
from subconscious_jobs import (
    PROMPT_VERSION as JOBS_PROMPT_VERSION,
)
from subconscious_jobs import (
    default_jobs_output_path,
)
from subconscious_runtime import (
    DEFAULT_TEMPERATURE,
    call_chat_json,
    compact_usage,
    parse_action,
)
from subconscious_worker import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_confidence

PROMPT_VERSION = "aippocampus-subconscious-review-v0"
DEFAULT_REVIEW_OUTPUT_NAME = "promotion_candidates.jsonl"
NAVIGATION_ONLY_JOBS = {"semantic_scope_labeling"}

REVIEW_SYSTEM_PROMPT = """You are AIppocampus subconscious review.
You review staging findings from prior subconscious jobs and decide what is
worth promoting into later workflows. You do not write formal memory. You do not
delete anything. Return only JSON.

Final schema:
{
  "action": "final",
    "promotion_candidates": [
    {
      "candidate_type": "concept_edge|hook_trigger|project_memory|preference_review|contradiction_review|dedup_review|question_candidate|frontier_marker|question_link|theme_candidate|archive",
      "title": "short title",
      "summary": "why this candidate matters",
      "recommendation": "what should consume or review it next",
      "confidence": 0.0,
      "source_finding_ids": ["sf_..."],
      "source_refs": [{"thread_key": "...", "line": 123}]
    }
  ],
  "duplicate_groups": [
    {"canonical_finding_id": "sf_...", "duplicate_finding_ids": ["sf_..."], "reason": "..."}
  ],
  "weak_findings": [
    {"finding_id": "sf_...", "reason": "why weak/noisy"}
  ]
}
"""


def default_review_output_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_REVIEW_OUTPUT_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_REVIEW_OUTPUT_NAME


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def normalize_finding(row: dict[str, Any]) -> dict[str, Any]:
    finding = dict(row)
    if finding.get("kind") == "aippocampus_subconscious_job_finding":
        finding["kind"] = finding.get("finding_kind") or ""
    finding.setdefault("fingerprint", finding_fingerprint(finding))
    finding.setdefault("quality", estimate_finding_quality(str(finding.get("job") or ""), finding))
    finding["summary"] = compact_text(str(finding.get("summary") or finding.get("why") or ""), 620)
    finding["recommendation"] = compact_text(str(finding.get("recommendation") or ""), 300)
    return finding


def recent_findings(
    path: Path, *, max_findings: int = 80, jobs: list[str] | None = None
) -> list[dict[str, Any]]:
    job_filter = {job for job in jobs or [] if job and job != "all"}
    rows = [normalize_finding(row) for row in iter_jsonl(path)]
    if job_filter:
        rows = [row for row in rows if str(row.get("job") or "") in job_filter]
    else:
        rows = [row for row in rows if str(row.get("job") or "") not in NAVIGATION_ONLY_JOBS]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows[: max(1, int(max_findings))]


def deterministic_duplicate_groups(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        groups[str(finding.get("fingerprint") or finding_fingerprint(finding))].append(finding)
    out = []
    for fingerprint, rows in groups.items():
        if len(rows) < 2:
            continue
        rows.sort(
            key=lambda row: float((row.get("quality") or {}).get("promotion_readiness") or 0.0),
            reverse=True,
        )
        out.append(
            {
                "fingerprint": fingerprint,
                "canonical_finding_id": rows[0].get("fingerprint"),
                "duplicate_finding_ids": [row.get("fingerprint") for row in rows[1:]],
                "reason": "same deterministic fingerprint",
            }
        )
    return out


def compact_review_payload(
    findings: list[dict[str, Any]], duplicate_groups: list[dict[str, Any]], focus: str = ""
) -> dict[str, Any]:
    # Findings are the large stable input. Focus is a run-specific lens, so keep
    # it after findings to preserve DeepSeek prefix-cache reuse across review
    # passes over the same staging set.
    payload = {
        "prompt_version": PROMPT_VERSION,
        "source_prompt_version": JOBS_PROMPT_VERSION,
        "task": "review_subconscious_findings_for_promotion",
        "findings": [
            {
                "finding_id": finding.get("fingerprint"),
                "job": finding.get("job"),
                "kind": finding.get("kind") or finding.get("finding_kind"),
                "title": finding.get("title"),
                "summary": finding.get("summary"),
                "recommendation": finding.get("recommendation"),
                "confidence": finding.get("confidence"),
                "quality": finding.get("quality"),
                "concepts": finding.get("concepts") or [],
                "src": finding.get("src"),
                "dst": finding.get("dst"),
                "edge_type": finding.get("edge_type"),
                "question_cluster_id": finding.get("question_cluster_id"),
                "linked_question_short": finding.get("linked_question_short"),
                "question_count": finding.get("question_count"),
                "link_type": finding.get("link_type"),
                "source_refs": [
                    {
                        "thread_key": ref.get("thread_key"),
                        "title": ref.get("title"),
                        "turn_index": ref.get("turn_index"),
                        "line": ref.get("source_line")
                        or ref.get("assistant_line")
                        or ref.get("user_line"),
                    }
                    for ref in finding.get("source_refs") or []
                    if isinstance(ref, dict)
                ][:5],
            }
            for finding in findings
        ],
        "deterministic_duplicate_groups": duplicate_groups[:20],
        "focus_rule": (
            "Prefer candidates inside the focus. Put off-focus findings into weak_findings "
            "unless they are clearly reusable global memory."
        ),
        "focus": focus,
    }
    return sanitize_external_model_payload(payload)


def validate_review(
    parsed: dict[str, Any], findings_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    candidates = []
    for item in parsed.get("promotion_candidates") or []:
        if not isinstance(item, dict):
            continue
        source_ids = unique_preserve(
            [str(value) for value in item.get("source_finding_ids") or [] if str(value).strip()],
            limit=12,
        )
        source_findings = [
            findings_by_id[source_id] for source_id in source_ids if source_id in findings_by_id
        ]
        if not source_findings:
            continue
        if any(
            str(finding.get("job") or "") in NAVIGATION_ONLY_JOBS for finding in source_findings
        ):
            continue
        confidence = clamp_confidence(item.get("confidence"))
        if confidence < 0.45:
            continue
        refs = []
        for finding in source_findings:
            for ref in finding.get("source_refs") or []:
                if isinstance(ref, dict):
                    refs.append(
                        {
                            "thread_key": ref.get("thread_key"),
                            "title": ref.get("title"),
                            "turn_index": ref.get("turn_index"),
                            "line": ref.get("source_line")
                            or ref.get("assistant_line")
                            or ref.get("user_line"),
                        }
                    )
        candidates.append(
            {
                "candidate_type": str(item.get("candidate_type") or "project_memory"),
                "title": compact_text(str(item.get("title") or ""), 160),
                "summary": compact_text(str(item.get("summary") or ""), 700),
                "recommendation": compact_text(str(item.get("recommendation") or ""), 360),
                "confidence": round(confidence, 4),
                "source_finding_ids": source_ids,
                "source_refs": refs[:8],
            }
        )
    duplicate_groups = []
    for item in parsed.get("duplicate_groups") or []:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical_finding_id") or "")
        duplicates = unique_preserve(
            [str(value) for value in item.get("duplicate_finding_ids") or [] if str(value).strip()],
            limit=24,
        )
        if canonical and duplicates:
            duplicate_groups.append(
                {
                    "canonical_finding_id": canonical,
                    "duplicate_finding_ids": duplicates,
                    "reason": compact_text(str(item.get("reason") or ""), 260),
                }
            )
    weak_findings = []
    for item in parsed.get("weak_findings") or []:
        if not isinstance(item, dict):
            continue
        finding_id = str(item.get("finding_id") or "")
        if finding_id in findings_by_id:
            weak_findings.append(
                {
                    "finding_id": finding_id,
                    "reason": compact_text(str(item.get("reason") or ""), 260),
                }
            )
    return {
        "promotion_candidates": candidates,
        "duplicate_groups": duplicate_groups,
        "weak_findings": weak_findings,
    }


def focus_score(candidate: dict[str, Any], focus: str) -> float:
    if not focus.strip():
        return 1.0
    terms = [term.casefold() for term in split_query_terms([focus]) if len(term.strip()) >= 3]
    if not terms:
        return 1.0
    blob = "\n".join(
        [
            str(candidate.get("candidate_type") or ""),
            str(candidate.get("title") or ""),
            str(candidate.get("summary") or ""),
            str(candidate.get("recommendation") or ""),
        ]
    ).casefold()
    score = 0.0
    for term in terms:
        if term in blob:
            score += min(2.0, max(0.4, len(term) / 12))
    return round(score, 4)


def apply_focus_filter(review: dict[str, Any], focus: str) -> dict[str, Any]:
    if not focus.strip():
        return review
    kept = []
    weak = list(review.get("weak_findings") or [])
    for candidate in review.get("promotion_candidates") or []:
        score = focus_score(candidate, focus)
        candidate["focus_score"] = score
        if score > 0:
            kept.append(candidate)
            continue
        for finding_id in candidate.get("source_finding_ids") or []:
            weak.append(
                {
                    "finding_id": finding_id,
                    "reason": f"off focus for review scope: {compact_text(focus, 120)}",
                }
            )
    review["promotion_candidates"] = kept
    review["weak_findings"] = weak
    return review


def append_review_output(
    path: Path,
    review: dict[str, Any],
    *,
    model: str,
    batch_id: str,
    usage: dict[str, Any],
    source: str = "deepseek_subconscious_review",
    model_route: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for candidate in review.get("promotion_candidates") or []:
            event = {
                "schema_version": 1,
                "kind": "aippocampus_promotion_candidate",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": model_route or {},
                "usage": usage or {},
                **candidate,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        for group in review.get("duplicate_groups") or []:
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_duplicate_group",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": model_route or {},
                **group,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        for weak in review.get("weak_findings") or []:
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_weak_finding",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": model_route or {},
                **weak,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_review(
    *,
    jobs_path: Path,
    output_path: Path,
    max_findings: int,
    jobs: list[str] | None,
    focus: str,
    model: str,
    base_url: str,
    api_key: str | None,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    model_route: str | None = None,
    max_tokens: int | None = None,
    timeout: int = 180,
    temperature: float = DEFAULT_TEMPERATURE,
    chat_fn=call_chat_json,
    no_write: bool = False,
) -> dict[str, Any]:
    findings = recent_findings(jobs_path, max_findings=max_findings, jobs=jobs)
    duplicate_groups = deterministic_duplicate_groups(findings)
    findings_by_id = {
        str(finding.get("fingerprint")): finding
        for finding in findings
        if finding.get("fingerprint")
    }
    batch_id = f"subconscious-review-{int(time.time())}"
    route = resolve_model_route(
        model_route,
        explicit_model=model if model != DEFAULT_MODEL and not model_route else None,
        explicit_base_url=base_url if base_url != DEFAULT_BASE_URL and not model_route else None,
        explicit_api_key_env=(
            api_key_env
            if api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV and not model_route
            else None
        ),
    )
    capabilities = route.capabilities
    resolved_model = route.model if model == DEFAULT_MODEL else model
    resolved_base_url = route.base_url if base_url == DEFAULT_BASE_URL else base_url
    resolved_api_key_env = (
        route.api_key_env
        if api_key_env == DEFAULT_DEEPSEEK_API_KEY_ENV
        else api_key_env
    )
    route_payload = route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )
    key_value = api_key or os.environ.get(resolved_api_key_env)
    if not key_value:
        raise RuntimeError(
            f"missing {route_service_name(route)} key; "
            f"set {resolved_api_key_env} or pass --api-key-env"
        )
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                compact_review_payload(findings, duplicate_groups, focus),
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]
    chat_kwargs = (
        {
            "service_name": route_service_name(route),
            "response_format_json": bool(
                capabilities.supports_json_response if capabilities else True
            ),
        }
        if chat_fn is call_chat_json
        else {}
    )
    response = chat_fn(
        messages,
        str(key_value),
        resolved_model,
        resolved_base_url,
        max_tokens,
        timeout,
        temperature,
        **chat_kwargs,
    )
    usage = compact_usage(response.get("usage") or {})
    parsed = parse_action(response)
    if parsed.get("action") != "final":
        parsed = {
            "promotion_candidates": [],
            "duplicate_groups": duplicate_groups,
            "weak_findings": [],
        }
    review = validate_review(parsed, findings_by_id)
    review = apply_focus_filter(review, focus)
    if not review["duplicate_groups"]:
        review["duplicate_groups"] = duplicate_groups
    if not no_write:
        append_review_output(
            output_path,
            review,
            model=resolved_model,
            batch_id=batch_id,
            usage=usage,
            source=route_artifact_source(route, "subconscious_review"),
            model_route=route_payload,
        )
    return {
        "ok": True,
        "jobs_path": str(jobs_path),
        "output": str(output_path),
        "finding_count": len(findings),
        "promotion_candidate_count": len(review["promotion_candidates"]),
        "duplicate_group_count": len(review["duplicate_groups"]),
        "weak_finding_count": len(review["weak_findings"]),
        "focus": focus,
        "review": review,
        "usage": usage,
        "cache": route_cache_metrics(route, usage),
        "model": resolved_model,
        "model_route": route_payload,
        "timeout": timeout,
        "temperature": temperature,
        "wrote": False if no_write else True,
        "batch_id": batch_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--output")
    parser.add_argument("--max-findings", type=int, default=80)
    parser.add_argument("--job", action="append", default=[])
    parser.add_argument("--focus", default="")
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else default_jobs_output_path(registry_path=registry_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_review_output_path(registry_path=registry_path)
    )
    try:
        result = run_review(
            jobs_path=jobs_path,
            output_path=output_path,
            max_findings=args.max_findings,
            jobs=args.job,
            focus=args.focus,
            model=args.model,
            base_url=args.base_url,
            api_key=None,
            api_key_env=args.api_key_env,
            model_route=args.model_route,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            temperature=args.temperature,
            no_write=args.no_write,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"findings reviewed: {result['finding_count']}")
        print(f"promotion candidates: {result['promotion_candidate_count']}")
        print(f"duplicate groups: {result['duplicate_group_count']}")
        print(f"weak findings: {result['weak_finding_count']}")
        print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
