#!/usr/bin/env python3
"""Recover suppressed semantic sidecar labels with a slow Pro agent.

This smoke does not relax the materializer. It asks a DeepSeek Pro route to
re-adjudicate labels that the strict sidecar gate suppressed, then runs the
recovered findings back through the same strict materializer helpers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    aippocampus_registry_dir,
    compact_text,
    deepseek_cache_metrics_from_usage,
    sanitize_external_model_payload,
)
from aippocampus_runtime.model.routing import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    NO_PROVIDER_CACHE_CONTRACT,
    deepseek_api_key_env,
    is_default_deepseek_api_key_env,
    resolve_model_route,
    route_cache_contract,
    route_cache_metrics,
    route_service_name,
)
from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.registry_paths import resolve_registry_member_path
from aippocampus_runtime.source.semantic_scope_labels import (
    canonical_scope_labels,
    clean_messages_by_id,
    filtered_semantic_scope_labels,
    is_semantic_scope_label_finding,
    iter_jsonl,
    label_evidence_map,
    label_evidence_min_confidence,
    semantic_scope_label_rows_from_findings,
)
from aippocampus_runtime.source.semantic_scope_source_review_core import (
    LABEL_GUIDANCE,
    parse_agent_action,
)
from aippocampus_runtime.subconscious.jobs import default_jobs_output_path
from aippocampus_runtime.subconscious.runtime import add_usage, call_chat_json, compact_usage
from aippocampus_runtime.subconscious.worker import DEFAULT_BASE_URL

PROMPT_KIND = "semantic_scope_suppressed_label_recovery"
PUBLIC_RECOVERY_STATUSES = {
    "observe_only",
    "live_model_missing_api_key",
    "sufficient",
    "insufficient_recovered_labels",
}
PUBLIC_CLAIM_LEVELS = {
    "diagnostic_only",
    "blocked_live_model",
    "pro_agent_suppressed_label_recovery",
}


def case_hash(*values: Any) -> str:
    return (
        "recover:"
        + hashlib.sha256(
            "\0".join(str(value or "") for value in values).encode("utf-8")
        ).hexdigest()[:16]
    )


def selected_suppressed_cases(
    registry_path: Path, jobs_output_path: Path, *, max_cases: int
) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    findings = [
        item for item in iter_jsonl(jobs_output_path) if is_semantic_scope_label_finding(item)
    ]
    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        messages_path = (
            resolve_registry_member_path(str(messages_path_value), registry_path)
            if messages_path_value
            else None
        )
        if not messages_path or not messages_path.exists():
            continue
        clean_source_dir = messages_path.parent
        messages_by_id = clean_messages_by_id(clean_source_dir)
        for finding in findings:
            message_id = str(finding.get("message_id") or "").strip()
            message = messages_by_id.get(message_id)
            if not message:
                continue
            proposed = canonical_scope_labels(
                list(finding.get("scope_labels") or finding.get("labels") or [])
            )
            accepted = set(filtered_semantic_scope_labels(finding, proposed))
            evidence = label_evidence_map(finding)
            suppressed = [
                label
                for label in proposed
                if label not in accepted
                and str((evidence.get(label) or {}).get("reason") or "").strip()
                and float((evidence.get(label) or {}).get("confidence") or 0.0) > 0.0
            ]
            if not suppressed:
                continue
            evidence_gaps = [
                max(
                    0.0,
                    label_evidence_min_confidence(label)
                    - float((evidence.get(label) or {}).get("confidence") or 0.0),
                )
                for label in suppressed
            ]
            candidates.append(
                {
                    "case_id": case_hash(entry.get("thread_key"), message_id, ",".join(suppressed)),
                    "thread_key": entry.get("thread_key"),
                    "message_id": message_id,
                    "turn_id": message.get("turn_id"),
                    "labels": suppressed,
                    "original_label_evidence": {
                        label: evidence.get(label) or {} for label in suppressed
                    },
                    "source_refs": finding.get("source_refs")
                    or [{"message_id": message_id, "source_line": message.get("source_line")}],
                    "text": compact_text(str(message.get("text") or ""), 1400),
                    "_selection_min_gap": min(evidence_gaps) if evidence_gaps else 1.0,
                    "_selection_avg_gap": sum(evidence_gaps) / len(evidence_gaps)
                    if evidence_gaps
                    else 1.0,
                }
            )
    candidates.sort(
        key=lambda item: (
            float(item.get("_selection_min_gap") or 1.0),
            float(item.get("_selection_avg_gap") or 1.0),
            -len(item.get("labels") or []),
            str(item.get("case_id") or ""),
        )
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        case_id = str(item.get("case_id") or "")
        if case_id in seen:
            continue
        seen.add(case_id)
        selected.append(
            {key: value for key, value in item.items() if not key.startswith("_selection_")}
        )
        if len(selected) >= max(1, int(max_cases)):
            break
    return selected


def recovery_messages(
    case: dict[str, Any], *, max_steps: int, min_tool_steps: int, model_route: str
) -> list[dict[str, str]]:
    payload = {
        "prompt_kind": PROMPT_KIND,
        "model_route": model_route,
        "instruction": (
            "Re-adjudicate suppressed semantic scope labels. First inspect the clean-source message with the tool. "
            "Return action=final with findings only for labels that can pass the strict materializer with stronger, "
            "source-grounded per-label evidence. Do not lower thresholds or keep labels that merely sound plausible."
        ),
        "output_schema_after_tool": {
            "action": "final",
            "findings": [
                {
                    "kind": "semantic_scope_labels",
                    "message_id": "use inspected source identity; do not invent ids",
                    "scope_labels": ["only recovered labels"],
                    "summary": "short source-grounded rationale without quoting private text",
                    "confidence": 0.0,
                    "label_evidence": [
                        {
                            "label": "label",
                            "reason": "specific source-grounded reason",
                            "confidence": 0.0,
                        }
                    ],
                    "source_refs": ["use inspected source refs"],
                }
            ],
        },
        "available_tools": {
            "inspect_suppressed_case": {
                "description": "Return clean-source message, suppressed labels, old evidence, thresholds, and exact source refs."
            }
        },
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "review_case": {
            "labels": case.get("labels") or [],
            "original_label_evidence": case.get("original_label_evidence") or {},
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are AIppocampus Pro slow adjudication for suppressed semantic sidecar labels. "
                "Return exactly one JSON object with action=tool or action=final."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def run_recovery_case(
    case: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    max_steps: int,
    min_tool_steps: int,
    chat_fn,
    model_route: str,
    chat_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages = recovery_messages(
        case, max_steps=max_steps, min_tool_steps=min_tool_steps, model_route=model_route
    )
    usage_total: dict[str, Any] = {}
    recovered_findings: list[dict[str, Any]] = []
    tool_step_count = 0
    for _step in range(max(1, int(max_steps))):
        response = chat_fn(
            sanitize_external_model_payload(messages),
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            **(chat_kwargs or {}),
        )
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_agent_action(response)
        if action.get("action") == "tool":
            if str(action.get("tool") or "") == "inspect_suppressed_case":
                observation = {
                    "ok": True,
                    "labels": case.get("labels") or [],
                    "original_label_evidence": case.get("original_label_evidence") or {},
                    "label_guidance_catalog": LABEL_GUIDANCE,
                    "label_evidence_min_confidence": {
                        label: label_evidence_min_confidence(label)
                        for label in case.get("labels") or []
                        if label in SCOPE_LABEL_ORDER
                    },
                    "clean_source_message": case.get("text") or "",
                    "source_identity_for_output": {
                        "message_id": case.get("message_id"),
                        "turn_id": case.get("turn_id"),
                    },
                    "source_refs": case.get("source_refs") or [],
                }
            else:
                observation = {"ok": False, "error": "unknown tool"}
            tool_step_count += 1
            messages.append(
                {"role": "assistant", "content": json.dumps(action, ensure_ascii=False)}
            )
            messages.append(
                {
                    "role": "user",
                    "content": "TOOL_RESULT:\n" + json.dumps(observation, ensure_ascii=False),
                }
            )
            continue
        if action.get("action") == "final":
            if tool_step_count < max(0, int(min_tool_steps)):
                messages.append(
                    {"role": "assistant", "content": json.dumps(action, ensure_ascii=False)}
                )
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"error": "Call inspect_suppressed_case before final."},
                            ensure_ascii=False,
                        ),
                    }
                )
                continue
            final_payload = action
            for key in ["result", "output"]:
                value = action.get(key)
                if isinstance(value, dict) and "findings" in value:
                    final_payload = value
                    break
            # The inspected case is the only source in the tool loop. Opaque
            # message ids/source refs are transport identity, not semantic
            # evidence, so normalize missing identity before applying the
            # unchanged strict evidence thresholds.
            recovered_findings = []
            for finding in final_payload.get("findings") or []:
                if not isinstance(finding, dict):
                    continue
                normalized = dict(finding)
                provided_message_id = str(normalized.get("message_id") or "").strip()
                if provided_message_id and provided_message_id != str(case.get("message_id") or ""):
                    continue
                normalized["message_id"] = case.get("message_id")
                refs = [
                    ref
                    for ref in normalized.get("source_refs") or []
                    if isinstance(ref, dict)
                    and str(ref.get("message_id") or "").strip()
                    == str(case.get("message_id") or "")
                ]
                normalized["source_refs"] = refs or list(case.get("source_refs") or [])
                recovered_findings.append(normalized)
            break
        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {"error": "Return action=tool or action=final only."}, ensure_ascii=False
                ),
            }
        )
    message = {
        "message_id": case.get("message_id"),
        "turn_id": case.get("turn_id"),
        "source_line": 0,
    }
    rows = semantic_scope_label_rows_from_findings(
        recovered_findings, {str(case.get("message_id")): message}
    )
    recovered_labels = sorted({label for row in rows for label in row.get("scope_labels") or []})
    cache_contract = str((chat_kwargs or {}).get("cache_contract") or "")
    cache = (
        {**deepseek_cache_metrics_from_usage(usage_total), "kind": "deepseek_prefix"}
        if cache_contract == DEEPSEEK_PREFIX_CACHE_CONTRACT
        else {"available": False, "kind": NO_PROVIDER_CACHE_CONTRACT}
    )
    return {
        "case_id": case.get("case_id"),
        "labels": case.get("labels") or [],
        "candidate_label_count": len(case.get("labels") or []),
        "strict_recovered_label_count": len(recovered_labels),
        "strict_recovered_labels": recovered_labels,
        "tool_step_count": tool_step_count,
        "usage": usage_total,
        "cache": cache,
    }


def per_label_recovery_stats(
    cases: list[dict[str, Any]], results: list[dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    candidate_counts = {
        label: sum(1 for case in cases if label in (case.get("labels") or []))
        for label in SCOPE_LABEL_ORDER
    }
    recovered_counts = {
        label: sum(
            1
            for item in results or []
            if label in (item.get("strict_recovered_labels") or [])
        )
        for label in SCOPE_LABEL_ORDER
    }
    reviewed = results is not None
    out: dict[str, dict[str, Any]] = {}
    for label in SCOPE_LABEL_ORDER:
        candidate_count = int(candidate_counts.get(label) or 0)
        recovered_count = int(recovered_counts.get(label) or 0)
        if not candidate_count and not recovered_count:
            continue
        still_suppressed = max(0, candidate_count - recovered_count) if reviewed else 0
        if not reviewed:
            status = "unreviewed"
        elif recovered_count:
            status = "recovered"
        else:
            status = "still_suppressed"
        out[label] = {
            "candidate_label_count": candidate_count,
            "strict_recovered_label_count": recovered_count,
            "strict_suppressed_label_count": still_suppressed,
            "status": status,
        }
    return out


def recovery_buckets(
    *, candidate_label_count: int, strict_recovered_label_count: int, reviewed: bool
) -> dict[str, int]:
    candidate_count = max(0, int(candidate_label_count))
    recovered_count = max(0, int(strict_recovered_label_count))
    return {
        "candidate_label_count": candidate_count,
        "strict_recovered_label_count": recovered_count,
        "strict_suppressed_label_count": max(0, candidate_count - recovered_count)
        if reviewed
        else 0,
        "unreviewed_label_count": 0 if reviewed else candidate_count,
    }


def run_suppressed_label_recovery_smoke(
    *,
    registry_path: str | Path | None = None,
    jobs_output_path: str | Path | None = None,
    live: bool = False,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    max_cases: int = 8,
    min_recovered_labels: int = 1,
    model: str | None = None,
    model_route: str = "suppressed_label_recovery",
    base_url: str = DEFAULT_BASE_URL,
    max_tokens: int | None = 2200,
    timeout: int = 180,
    max_steps: int = 3,
    min_tool_steps: int = 1,
    chat_fn=None,
) -> dict[str, Any]:
    registry = (
        Path(registry_path).resolve()
        if registry_path
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    jobs_output = (
        Path(jobs_output_path).resolve()
        if jobs_output_path
        else default_jobs_output_path(registry_path=registry)
    )
    route = resolve_model_route(model_route, explicit_model=model)
    resolved_base_url = route.base_url if base_url == DEFAULT_BASE_URL else base_url
    cases = selected_suppressed_cases(registry, jobs_output, max_cases=max_cases)
    privacy_boundary = {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "titles_emitted": False,
        "source_reference_details_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": True,
        "strict_gate_relaxed": False,
        "external_model_call_requires_live_flag": True,
    }
    if not live:
        candidate_label_count = sum(len(case.get("labels") or []) for case in cases)
        return {
            "ok": len(cases) > 0,
            "status": "observe_only",
            "claim_level": "diagnostic_only",
            "live_model_used": False,
            "model_route": route.as_dict(),
            "case_count": len(cases),
            "candidate_label_count": candidate_label_count,
            "strict_recovered_label_count": 0,
            "strict_gate_relaxed": False,
            "per_label_recovery": per_label_recovery_stats(cases),
            "recovery_buckets": recovery_buckets(
                candidate_label_count=candidate_label_count,
                strict_recovered_label_count=0,
                reviewed=False,
            ),
            "label_coverage": sorted(
                {label for case in cases for label in case.get("labels") or []}
            ),
            "cases": [],
            "privacy_boundary": privacy_boundary,
        }
    resolved_api_key_env = (
        deepseek_api_key_env(os.environ)
        if is_default_deepseek_api_key_env(api_key_env)
        else api_key_env
    )
    api_key = os.environ.get(resolved_api_key_env)
    if not api_key:
        candidate_label_count = sum(len(case.get("labels") or []) for case in cases)
        return {
            "ok": False,
            "status": "live_model_missing_api_key",
            "claim_level": "blocked_live_model",
            "live_model_used": False,
            "model_route": route.as_dict(),
            "case_count": len(cases),
            "candidate_label_count": candidate_label_count,
            "strict_recovered_label_count": 0,
            "strict_gate_relaxed": False,
            "per_label_recovery": per_label_recovery_stats(cases),
            "recovery_buckets": recovery_buckets(
                candidate_label_count=candidate_label_count,
                strict_recovered_label_count=0,
                reviewed=False,
            ),
            "label_coverage": sorted(
                {label for case in cases for label in case.get("labels") or []}
            ),
            "cases": [],
            "privacy_boundary": privacy_boundary,
        }
    reviewer = chat_fn or call_chat_json
    live_chat_kwargs = (
        {
            "cache_contract": route_cache_contract(route),
            "service_name": route_service_name(route),
            "response_format_json": True,
        }
        if reviewer is call_chat_json
        else None
    )
    results = [
        run_recovery_case(
            case,
            api_key=api_key,
            model=route.model,
            base_url=resolved_base_url,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=0.0,
            max_steps=max_steps,
            min_tool_steps=min_tool_steps,
            chat_fn=reviewer,
            model_route=route.route,
            chat_kwargs=live_chat_kwargs,
        )
        for case in cases
    ]
    usage_total: dict[str, Any] = {}
    for item in results:
        add_usage(usage_total, item.get("usage") or {})
    candidate_label_count = sum(len(case.get("labels") or []) for case in cases)
    recovered_count = sum(int(item.get("strict_recovered_label_count") or 0) for item in results)
    status = (
        "sufficient"
        if recovered_count >= int(min_recovered_labels)
        else "insufficient_recovered_labels"
    )
    return {
        "ok": status == "sufficient",
        "status": status,
        "claim_level": "pro_agent_suppressed_label_recovery"
        if status == "sufficient"
        else "diagnostic_only",
        "live_model_used": True,
        "model_route": route.as_dict(),
        "case_count": len(cases),
        "candidate_label_count": candidate_label_count,
        "strict_recovered_label_count": recovered_count,
        "strict_gate_relaxed": False,
        "per_label_recovery": per_label_recovery_stats(cases, results),
        "recovery_buckets": recovery_buckets(
            candidate_label_count=candidate_label_count,
            strict_recovered_label_count=recovered_count,
            reviewed=True,
        ),
        "label_coverage": sorted({label for case in cases for label in case.get("labels") or []}),
        "recovered_label_coverage": sorted(
            {label for item in results for label in item.get("strict_recovered_labels") or []}
        ),
        "usage": usage_total,
        "cache": route_cache_metrics(route, usage_total),
        "cases": results,
        "privacy_boundary": privacy_boundary,
        "boundary": "Pro-agent recovery proposes stronger sidecar findings, then the unchanged strict materializer decides what can be recovered.",
    }


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_token(value: Any, *, allowed: set[str] | None = None, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    safe = "".join(char for char in text[:80] if char.isalnum() or char in {"_", "-", "."})
    if not safe:
        return fallback
    if allowed is not None and safe not in allowed:
        return fallback
    return safe


def public_label_list(values: Any, *, limit: int = 24) -> list[str]:
    labels: list[str] = []
    for value in values or []:
        label = public_token(value, fallback="")
        if label:
            labels.append(label)
    return sorted(set(labels))[:limit]


def public_model_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, dict):
        return {}
    return {
        "provider": public_token(route.get("provider"), fallback="unknown"),
        "route": public_token(route.get("route"), fallback="unknown"),
    }


def public_usage(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in usage:
            out[key] = public_count(usage.get(key))
    return out


def public_cache(cache: Any) -> dict[str, Any]:
    if not isinstance(cache, dict):
        return {}
    return {
        "available": bool(cache.get("available")),
        "kind": public_token(cache.get("kind"), fallback="unknown"),
    }


def public_recovery_buckets(buckets: Any) -> dict[str, int]:
    if not isinstance(buckets, dict):
        return {}
    return {
        "candidate_label_count": public_count(buckets.get("candidate_label_count")),
        "strict_recovered_label_count": public_count(
            buckets.get("strict_recovered_label_count")
        ),
        "strict_suppressed_label_count": public_count(
            buckets.get("strict_suppressed_label_count")
        ),
        "unreviewed_label_count": public_count(buckets.get("unreviewed_label_count")),
    }


def public_per_label_recovery(stats: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(stats, dict):
        return {}
    allowed_status = {"unreviewed", "recovered", "still_suppressed"}
    out: dict[str, dict[str, Any]] = {}
    for label in SCOPE_LABEL_ORDER:
        item = stats.get(label)
        if not isinstance(item, dict):
            continue
        out[label] = {
            "candidate_label_count": public_count(item.get("candidate_label_count")),
            "strict_recovered_label_count": public_count(
                item.get("strict_recovered_label_count")
            ),
            "strict_suppressed_label_count": public_count(
                item.get("strict_suppressed_label_count")
            ),
            "status": public_token(
                item.get("status"), allowed=allowed_status, fallback="unreviewed"
            ),
        }
    return out


def public_privacy_boundary(boundary: Any) -> dict[str, Any]:
    if not isinstance(boundary, dict):
        return {}
    return {
        "raw_text_emitted": bool(boundary.get("raw_text_emitted")),
        "snippets_emitted": bool(boundary.get("snippets_emitted")),
        "titles_emitted": bool(boundary.get("titles_emitted")),
        "source_reference_details_emitted": bool(
            boundary.get("source_reference_details_emitted")
        ),
        "absolute_paths_emitted": bool(boundary.get("absolute_paths_emitted")),
        "case_ids_are_hashed": bool(boundary.get("case_ids_are_hashed")),
        "strict_gate_relaxed": bool(boundary.get("strict_gate_relaxed")),
        "external_model_call_requires_live_flag": bool(
            boundary.get("external_model_call_requires_live_flag")
        ),
    }


def public_smoke_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(result.get("ok")),
        "status": public_token(
            result.get("status"),
            allowed=PUBLIC_RECOVERY_STATUSES,
            fallback="unknown",
        ),
        "claim_level": public_token(
            result.get("claim_level"),
            allowed=PUBLIC_CLAIM_LEVELS,
            fallback="diagnostic_only",
        ),
        "live_model_used": bool(result.get("live_model_used")),
        "model_route": public_model_route(result.get("model_route")),
        "case_count": public_count(result.get("case_count")),
        "candidate_label_count": public_count(result.get("candidate_label_count")),
        "strict_recovered_label_count": public_count(
            result.get("strict_recovered_label_count")
        ),
        "strict_gate_relaxed": bool(result.get("strict_gate_relaxed")),
        "recovery_buckets": public_recovery_buckets(result.get("recovery_buckets")),
        "per_label_recovery": public_per_label_recovery(
            result.get("per_label_recovery")
        ),
        "label_coverage": public_label_list(result.get("label_coverage")),
        "recovered_label_coverage": public_label_list(result.get("recovered_label_coverage")),
        "usage": public_usage(result.get("usage")),
        "cache": public_cache(result.get("cache")),
        "privacy_boundary": public_privacy_boundary(result.get("privacy_boundary")),
        "output_boundary": "case details omitted from CLI output; source-backed jobs remain local",
    }


def write_stdout_line(text: str) -> None:
    os.write(1, f"{text}\n".encode("utf-8"))


def emit_smoke_result(result: dict[str, Any], *, json_output: bool) -> None:
    public_result = public_smoke_result(result)
    if json_output:
        json.dump(public_result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return
    write_stdout_line(f"suppressed label recovery: {public_result.get('status')}")
    write_stdout_line(
        f"strict recovered labels: {public_result.get('strict_recovered_label_count')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--jobs-output")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--max-cases", type=int, default=8)
    parser.add_argument("--min-recovered-labels", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--model-route", default="suppressed_label_recovery")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=2200)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--min-tool-steps", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    result = run_suppressed_label_recovery_smoke(
        registry_path=args.registry,
        jobs_output_path=args.jobs_output,
        live=args.live,
        api_key_env=args.api_key_env,
        max_cases=args.max_cases,
        min_recovered_labels=args.min_recovered_labels,
        model=args.model,
        model_route=args.model_route,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        max_steps=args.max_steps,
        min_tool_steps=args.min_tool_steps,
    )
    emit_smoke_result(result, json_output=args.json_output)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
