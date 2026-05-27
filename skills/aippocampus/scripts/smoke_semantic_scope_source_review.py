#!/usr/bin/env python3
"""Live source-review smoke for semantic scope-label sidecars.

Semantic sidecars are navigation hints. This smoke samples materialized
`semantic-scope-labels.jsonl` rows, sends the matching clean-source message and
labels to a DeepSeek-compatible reviewer, and checks whether the labels are
supported by the source text. Output is sanitized: no raw text, titles, paths,
message ids, or source refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from aippocampuslib import aippocampus_registry_dir, compact_text, deepseek_cache_metrics_from_usage, sanitize_external_model_payload
from build_clean_source import SCOPE_LABEL_ORDER
from build_project_timeline import resolve_registry_member_path
from deepseek_model_routing import resolve_model_route
from registry import load_registry
from semantic_scope_labels import clean_messages_by_id, load_semantic_scope_labels
from subconscious_agent import add_usage, call_chat_json, compact_usage
from subconscious_worker import DEFAULT_BASE_URL


PROMPT_KIND = "semantic_scope_label_source_review"
LABEL_GUIDANCE = {
    "personal_reflection": "The user is reflecting on self, feelings, doubts, identity, or meaning.",
    "relationship_continuity": "The message depends on continuity with prior conversations or an ongoing relationship.",
    "reading_notes": "The message records, reacts to, or discusses reading material.",
    "idea_seed": "The message contains an early idea, metaphor, direction, or creative spark worth tracking.",
    "preference": "The user states a stable or situational preference about how things should be done.",
    "life_context": "The message concerns life circumstances, day-to-day context, body, schedule, mood, or lived situation.",
    "technical_work": "The message concerns implementation, repo work, tools, code, architecture, tests, or technical decisions.",
    "open_question": "The message contains an unresolved question, uncertainty, or inquiry to continue later.",
}


def evidence_hash(*values: Any) -> str:
    text = "\0".join(str(value or "") for value in values)
    return "review:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def selected_review_cases(registry_path: Path, *, max_cases: int, min_confidence: float = 0.45) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        messages_path = resolve_registry_member_path(str(messages_path_value), registry_path) if messages_path_value else None
        if not messages_path or not messages_path.exists():
            continue
        clean_source_dir = messages_path.parent
        messages_by_id = clean_messages_by_id(clean_source_dir)
        sidecar = load_semantic_scope_labels(clean_source_dir)
        for message_id, row in sidecar.items():
            message = messages_by_id.get(message_id)
            if not message:
                continue
            labels = [label for label in row.get("scope_labels") or [] if label in SCOPE_LABEL_ORDER]
            confidence = float(row.get("confidence") or 0.0)
            if not labels or confidence < min_confidence:
                continue
            evidence_by_label = {
                str(item.get("label") or ""): {
                    "reason": compact_text(str(item.get("reason") or ""), 180),
                    "confidence": float(item.get("confidence") or 0.0),
                }
                for item in row.get("label_evidence") or []
                if isinstance(item, dict) and str(item.get("label") or "") in labels
            }
            for label in labels:
                candidates.append(
                    {
                        "case_id": evidence_hash(entry.get("thread_key"), message_id, message.get("turn_id"), label),
                        "thread_key": entry.get("thread_key"),
                        "message_id": message_id,
                        "turn_id": message.get("turn_id"),
                        "labels": [label],
                        "label_evidence": {label: evidence_by_label.get(label) or {}},
                        "confidence": confidence,
                        "text": compact_text(str(message.get("text") or ""), 1200),
                    }
                )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Review one label per case. Round-robin across labels so the smoke does
    # not overfit to the most frequent sidecar label in the current registry.
    buckets: dict[str, list[dict[str, Any]]] = {
        label: [
            case
            for case in sorted(candidates, key=lambda item: (-float(item.get("confidence") or 0.0), str(item.get("case_id") or "")))
            if label in case.get("labels", [])
        ]
        for label in SCOPE_LABEL_ORDER
    }
    while len(selected) < max(1, int(max_cases)):
        progressed = False
        for label in SCOPE_LABEL_ORDER:
            bucket = buckets.get(label) or []
            while bucket:
                case = bucket.pop(0)
                if case["case_id"] in seen:
                    continue
                selected.append(case)
                seen.add(case["case_id"])
                progressed = True
                break
            if len(selected) >= max(1, int(max_cases)):
                return selected
        if not progressed:
            break
    for case in sorted(candidates, key=lambda item: (-float(item.get("confidence") or 0.0), str(item.get("case_id") or ""))):
        if case["case_id"] in seen:
            continue
        selected.append(case)
        seen.add(case["case_id"])
        if len(selected) >= max(1, int(max_cases)):
            break
    return selected


def review_messages(case: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "prompt_kind": PROMPT_KIND,
        "instruction": (
            "Review whether each proposed semantic scope label is supported by the clean-source message. "
            "Also review whether the proposed label_evidence gives a specific source-grounded reason for that label. "
            "Use semantic judgment, not keyword matching. Return JSON only."
        ),
        # Keep the full guidance catalog and schema before the variable review
        # case. Broad review smokes send many different messages; a stable
        # prefix lets DeepSeek reuse the reviewer contract instead of only the
        # tiny system prompt. Do not move review_case earlier for tidiness.
        "label_guidance_catalog": LABEL_GUIDANCE,
        "output_schema": {
            "supported_labels": ["labels from input that are supported"],
            "unsupported_labels": ["labels from input that are not supported"],
            "unsupported_evidence_labels": ["labels whose proposed evidence is missing, generic, or unsupported by the message"],
            "confidence": 0.0,
            "needs_human_review": False,
        },
        "review_case": {
            "labels": case.get("labels") or [],
            "label_evidence": case.get("label_evidence") or {},
            "clean_source_message": case.get("text") or "",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict source-evidence reviewer for AIppocampus semantic sidecars. "
                "Do not invent context outside the provided message. Return exactly one JSON object."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    return str(((choices[0].get("message") or {}).get("content") or "").strip())


def parse_review_response(response: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    parsed = json.loads(response_content(response))
    return parse_review_payload(parsed if isinstance(parsed, dict) else {}, labels)


def parse_review_payload(parsed: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        parsed = {}
    proposed = {label for label in labels if label in SCOPE_LABEL_ORDER}
    supported = [label for label in parsed.get("supported_labels") or [] if label in proposed]
    unsupported = [label for label in parsed.get("unsupported_labels") or [] if label in proposed]
    unsupported_evidence = [
        label
        for label in parsed.get("unsupported_evidence_labels") or parsed.get("evidence_unsupported_labels") or []
        if label in proposed
    ]
    missing = [label for label in labels if label in proposed and label not in supported and label not in unsupported]
    unsupported = list(dict.fromkeys([*unsupported, *unsupported_evidence, *missing]))
    supported = [label for label in supported if label not in unsupported]
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "supported_labels": supported,
        "unsupported_labels": unsupported,
        "confidence": max(0.0, min(1.0, confidence)),
        "needs_human_review": bool(parsed.get("needs_human_review")),
    }


def final_review_payload(action: dict[str, Any]) -> dict[str, Any]:
    if any(key in action for key in ["supported_labels", "unsupported_labels", "unsupported_evidence_labels"]):
        return action
    for key in ["review", "result", "output"]:
        value = action.get(key)
        if isinstance(value, dict):
            return value
    return action


def parse_agent_action(response: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(response_content(response))
    except json.JSONDecodeError as exc:
        return {"action": "parse_error", "error": str(exc)}
    return parsed if isinstance(parsed, dict) else {"action": "parse_error", "error": "non-object response"}


def review_case(
    case: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    min_review_confidence: float,
    max_attempts: int,
    chat_fn,
) -> dict[str, Any]:
    attempts = max(1, int(max_attempts))
    last_error: BaseException | None = None
    response: dict[str, Any] | None = None
    for _attempt in range(attempts):
        try:
            response = chat_fn(
                sanitize_external_model_payload(review_messages(case)),
                api_key,
                model,
                base_url,
                max_tokens,
                timeout,
                temperature,
            )
            break
        except Exception as exc:
            last_error = exc
    if response is None:
        if last_error:
            raise last_error
        raise RuntimeError("reviewer returned no response")
    review = parse_review_response(response, list(case.get("labels") or []))
    usage = compact_usage(response.get("usage") or {})
    passed = (
        not review["unsupported_labels"]
        and not review["needs_human_review"]
        and float(review["confidence"]) >= min_review_confidence
    )
    return {
        "case_id": case.get("case_id"),
        "prompt_kind": PROMPT_KIND,
        "labels": case.get("labels") or [],
        "passed": bool(passed),
        "supported_label_count": len(review["supported_labels"]),
        "unsupported_label_count": len(review["unsupported_labels"]),
        "needs_human_review": review["needs_human_review"],
        "review_confidence": round(float(review["confidence"]), 4),
        "attempt_count": attempts if last_error else 1,
        "usage": usage,
        "cache": deepseek_cache_metrics_from_usage(usage),
    }


def agentic_review_messages(case: dict[str, Any], *, max_steps: int, min_tool_steps: int) -> list[dict[str, str]]:
    payload = {
        "prompt_kind": PROMPT_KIND,
        "review_mode": "agentic_source_review",
        "instruction": (
            "Review one semantic sidecar label case. First inspect the clean-source message with the available tool, "
            "then return action=final with supported_labels, unsupported_labels, unsupported_evidence_labels, "
            "confidence, and needs_human_review."
        ),
        "label_guidance_catalog": LABEL_GUIDANCE,
        "available_tools": {
            "inspect_review_case": {
                "description": "Return the clean-source message, proposed labels, and proposed label evidence for this case."
            }
        },
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "review_case": {
            "labels": case.get("labels") or [],
            "label_evidence": case.get("label_evidence") or {},
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict agentic source-evidence reviewer for AIppocampus semantic sidecars. "
                "Return exactly one JSON object with action=tool or action=final."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def review_case_agentic(
    case: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    min_review_confidence: float,
    max_steps: int,
    min_tool_steps: int,
    chat_fn,
) -> dict[str, Any]:
    messages = agentic_review_messages(case, max_steps=max_steps, min_tool_steps=min_tool_steps)
    usage_total: dict[str, Any] = {}
    tool_step_count = 0
    review: dict[str, Any] | None = None
    for _step in range(max(1, int(max_steps))):
        response = chat_fn(
            sanitize_external_model_payload(messages),
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
        )
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_agent_action(response)
        if action.get("action") == "tool":
            if str(action.get("tool") or "") != "inspect_review_case":
                observation = {"ok": False, "error": "unknown tool"}
            else:
                observation = {
                    "ok": True,
                    "labels": case.get("labels") or [],
                    "label_evidence": case.get("label_evidence") or {},
                    "label_guidance_catalog": LABEL_GUIDANCE,
                    "clean_source_message": case.get("text") or "",
                }
            tool_step_count += 1
            messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
            messages.append({"role": "user", "content": "TOOL_RESULT:\n" + json.dumps(observation, ensure_ascii=False)})
            continue
        if action.get("action") == "final":
            if tool_step_count < max(0, int(min_tool_steps)):
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append({"role": "user", "content": json.dumps({"error": "Call inspect_review_case before final."}, ensure_ascii=False)})
                continue
            review = parse_review_payload(final_review_payload(action), list(case.get("labels") or []))
            break
        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append({"role": "user", "content": json.dumps({"error": "Return action=tool or action=final only."}, ensure_ascii=False)})
    if review is None:
        review = {
            "supported_labels": [],
            "unsupported_labels": [label for label in case.get("labels") or [] if label in SCOPE_LABEL_ORDER],
            "confidence": 0.0,
            "needs_human_review": True,
        }
    passed = (
        not review["unsupported_labels"]
        and not review["needs_human_review"]
        and float(review["confidence"]) >= min_review_confidence
    )
    return {
        "case_id": case.get("case_id"),
        "prompt_kind": PROMPT_KIND,
        "review_mode": "agentic",
        "labels": case.get("labels") or [],
        "passed": bool(passed),
        "supported_label_count": len(review["supported_labels"]),
        "unsupported_label_count": len(review["unsupported_labels"]),
        "needs_human_review": review["needs_human_review"],
        "review_confidence": round(float(review["confidence"]), 4),
        "tool_step_count": tool_step_count,
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
    }


def review_status(case_count: int, passed_count: int, *, min_cases: int, min_pass_rate: float) -> str:
    if case_count < min_cases:
        return "insufficient_selected_cases"
    pass_rate = (passed_count / case_count) if case_count else 0.0
    if pass_rate < min_pass_rate:
        return "insufficient_source_review_pass_rate"
    return "sufficient"


def per_label_review_stats(review_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for label in SCOPE_LABEL_ORDER:
        items = [item for item in review_results if label in (item.get("labels") or [])]
        if not items:
            continue
        passed_count = sum(1 for item in items if item.get("passed"))
        out[label] = {
            "case_count": len(items),
            "passed_count": passed_count,
            "failed_count": max(0, len(items) - passed_count),
            "pass_rate": round(passed_count / len(items), 4),
        }
    return out


def failed_label_categories(per_label: dict[str, dict[str, Any]], *, min_label_pass_rate: float) -> list[str]:
    return [
        label
        for label, stats in per_label.items()
        if int(stats.get("case_count") or 0) > 0 and float(stats.get("pass_rate") or 0.0) < min_label_pass_rate
    ]


def cannot_claim(status: str, *, live: bool) -> list[str]:
    claims = [
        "global_semantic_label_correctness",
        "human_reviewed_label_correctness",
        "semantic_completeness",
    ]
    if not live:
        claims.append("fresh_live_model_review")
    if status != "sufficient":
        claims.append("selected_source_review_passed")
    return claims


def run_semantic_scope_source_review(
    *,
    registry_path: str | Path | None = None,
    live: bool = False,
    api_key_env: str = "DEEPSEEK_API_KEY",
    max_cases: int = 16,
    min_cases: int = 8,
    min_pass_rate: float = 0.75,
    min_label_pass_rate: float = 0.65,
    min_review_confidence: float = 0.65,
    concurrency: int = 6,
    model: str | None = None,
    model_route: str = "default",
    base_url: str = DEFAULT_BASE_URL,
    max_tokens: int | None = 900,
    timeout: int = 90,
    max_attempts: int = 2,
    agentic_review: bool = False,
    review_max_steps: int = 3,
    min_tool_steps: int = 1,
    chat_fn=None,
) -> dict[str, Any]:
    resolved_route = resolve_model_route(
        "agentic_source_review" if agentic_review and model_route == "default" and not model else model_route,
        explicit_model=model,
    )
    registry = Path(registry_path).resolve() if registry_path else (aippocampus_registry_dir() / "threads.json").resolve()
    cases = selected_review_cases(registry, max_cases=max_cases)
    privacy_boundary = {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "titles_emitted": False,
        "source_reference_details_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": True,
        "external_model_call_requires_live_flag": True,
        "live_mode_missing_api_key_fails": True,
    }
    if not live:
        status = "observe_only"
        return {
            "ok": len(cases) >= min_cases,
            "status": status,
            "claim_level": "diagnostic_only",
            "cannot_claim": cannot_claim(status, live=False),
            "live_model_used": False,
            "case_count": len(cases),
            "passed_count": 0,
            "pass_rate": 0.0,
            "per_label": {},
            "failed_label_categories": [],
            "min_label_pass_rate": float(min_label_pass_rate),
            "label_coverage": sorted({label for case in cases for label in case.get("labels") or []}),
            "model_route": resolved_route.as_dict(),
            "cases": [],
            "privacy_boundary": privacy_boundary,
        }
    api_key = os.environ.get(api_key_env)
    if not api_key:
        status = "live_model_missing_api_key"
        return {
            "ok": False,
            "status": status,
            "claim_level": "blocked_live_model",
            "cannot_claim": cannot_claim(status, live=True),
            "live_model_used": False,
            "case_count": len(cases),
            "passed_count": 0,
            "pass_rate": 0.0,
            "per_label": {},
            "failed_label_categories": [],
            "min_label_pass_rate": float(min_label_pass_rate),
            "label_coverage": sorted({label for case in cases for label in case.get("labels") or []}),
            "model_route": resolved_route.as_dict(),
            "cases": [],
            "privacy_boundary": privacy_boundary,
        }

    review_results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    failures = 0
    reviewer = chat_fn or call_chat_json
    max_workers = min(max(1, int(concurrency)), max(1, len(cases)))

    def failed_case(case: dict[str, Any], exc: BaseException) -> dict[str, Any]:
        return {
            "case_id": case.get("case_id"),
            "prompt_kind": PROMPT_KIND,
            "labels": case.get("labels") or [],
            "passed": False,
            "supported_label_count": 0,
            "unsupported_label_count": len(case.get("labels") or []),
            "needs_human_review": True,
            "review_confidence": 0.0,
            "error": compact_text(f"{type(exc).__name__}: {exc}", 180),
            "usage": {},
            "cache": deepseek_cache_metrics_from_usage({}),
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                review_case_agentic if agentic_review else review_case,
                case,
                api_key=api_key,
                model=resolved_route.model,
                base_url=base_url,
                max_tokens=max_tokens,
                timeout=timeout,
                temperature=0.0,
                min_review_confidence=min_review_confidence,
                **(
                    {
                        "max_steps": review_max_steps,
                        "min_tool_steps": min_tool_steps,
                    }
                    if agentic_review
                    else {"max_attempts": max_attempts}
                ),
                chat_fn=reviewer,
            ): case
            for case in cases
        }
        for future in as_completed(futures):
            case = futures[future]
            try:
                review_results.append(future.result())
            except Exception as exc:
                failures += 1
                review_results.append(failed_case(case, exc))
    review_results.sort(key=lambda item: str(item.get("case_id") or ""))
    for item in review_results:
        add_usage(usage_total, item.get("usage") or {})
    passed_count = sum(1 for item in review_results if item.get("passed"))
    status = review_status(len(cases), passed_count, min_cases=min_cases, min_pass_rate=min_pass_rate)
    pass_rate = round((passed_count / len(cases)) if cases else 0.0, 4)
    per_label = per_label_review_stats(review_results)
    return {
        "ok": status == "sufficient" and failures == 0,
        "status": status if failures == 0 else "live_model_partial_failure",
        "claim_level": "selected_semantic_label_source_review" if status == "sufficient" and failures == 0 else "diagnostic_only",
        "cannot_claim": cannot_claim(status, live=True),
        "live_model_used": True,
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": max(0, len(cases) - passed_count),
        "pass_rate": pass_rate,
        "min_cases": int(min_cases),
        "min_pass_rate": float(min_pass_rate),
        "min_label_pass_rate": float(min_label_pass_rate),
        "min_review_confidence": float(min_review_confidence),
        "concurrency": max_workers,
        "max_attempts": max(1, int(max_attempts)),
        "review_mode": "agentic" if agentic_review else "single_prompt",
        "label_coverage": sorted({label for case in cases for label in case.get("labels") or []}),
        "model_route": resolved_route.as_dict(),
        "failure_count": failures,
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
        "per_label": per_label,
        "failed_label_categories": failed_label_categories(per_label, min_label_pass_rate=min_label_pass_rate),
        "cases": review_results,
        "privacy_boundary": privacy_boundary,
        "boundary": "DeepSeek-compatible review checks selected sidecar labels against clean source; it is not human review or global correctness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--max-cases", type=int, default=16)
    parser.add_argument("--min-cases", type=int, default=8)
    parser.add_argument("--min-pass-rate", type=float, default=0.75)
    parser.add_argument("--min-label-pass-rate", type=float, default=0.65)
    parser.add_argument("--min-review-confidence", type=float, default=0.65)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--model")
    parser.add_argument("--model-route", default="default")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--agentic-review", action="store_true")
    parser.add_argument("--review-max-steps", type=int, default=3)
    parser.add_argument("--min-tool-steps", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    result = run_semantic_scope_source_review(
        registry_path=args.registry,
        live=args.live,
        api_key_env=args.api_key_env,
        max_cases=args.max_cases,
        min_cases=args.min_cases,
        min_pass_rate=args.min_pass_rate,
        min_label_pass_rate=args.min_label_pass_rate,
        min_review_confidence=args.min_review_confidence,
        concurrency=args.concurrency,
        model=args.model,
        model_route=args.model_route,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        max_attempts=args.max_attempts,
        agentic_review=args.agentic_review,
        review_max_steps=args.review_max_steps,
        min_tool_steps=args.min_tool_steps,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic scope source review: {result.get('status')}")
        print(f"cases: {result.get('case_count')} passed: {result.get('passed_count')} pass_rate: {result.get('pass_rate')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
