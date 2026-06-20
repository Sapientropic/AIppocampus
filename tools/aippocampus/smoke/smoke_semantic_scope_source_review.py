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

import _paths

_paths.ensure_paths()

from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref

from aippocampus_runtime.core import (
    aippocampus_registry_dir,
    compact_text,
    deepseek_cache_metrics_from_usage,
    sanitize_external_model_payload,
)
from aippocampus_runtime.model.routing import resolve_model_route
from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.registry_paths import resolve_registry_member_path
from aippocampus_runtime.source.semantic_scope_labels import (
    clean_messages_by_id,
    load_semantic_scope_labels,
)
from aippocampus_runtime.source.semantic_scope_source_review_core import (
    LABEL_GUIDANCE,
    parse_agent_action,
    response_content,
)
from aippocampus_runtime.subconscious.runtime import add_usage, call_chat_json, compact_usage
from aippocampus_runtime.subconscious.worker import DEFAULT_BASE_URL

PROMPT_KIND = "semantic_scope_label_source_review"
REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_SHADOW_REGISTRY = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "semantic_scope_source_review_shadow"
    / "registry"
    / "threads.json"
)
PUBLIC_SHADOW_REQUIREMENT_KEYS = [
    "source_open_positive",
    "stale_or_superseded_source",
    "unsupported_semantic_sidecar",
    "multilingual_paraphrase",
    "preference_source_open_positive",
    "preference_unsupported_generic_claim",
    "preference_stale_currentness_boundary",
]
REVIEW_FAILURE_CLASSES = [
    "timeout",
    "provider_transport_error",
    "provider_response_shape",
    "retry_exhaustion",
    "prompt_context_issue",
    "source_open_issue",
    "report_aggregation_bug",
    "unexpected_exception",
]
LABEL_FAILURE_CLASSES = [
    "unsupported_label",
    "unsupported_label_evidence",
    "stale_or_currentness_boundary",
    "human_review_boundary",
    "low_review_confidence",
    "operational_failure",
]


def evidence_hash(*values: Any) -> str:
    text = "\0".join(str(value or "") for value in values)
    return "review:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def selected_review_cases(
    registry_path: Path, *, max_cases: int, min_confidence: float = 0.45
) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
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
        sidecar = load_semantic_scope_labels(clean_source_dir)
        for message_id, row in sidecar.items():
            message = messages_by_id.get(message_id)
            if not message:
                continue
            labels = [
                label for label in row.get("scope_labels") or [] if label in SCOPE_LABEL_ORDER
            ]
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
                        "case_id": evidence_hash(
                            entry.get("thread_key"), message_id, message.get("turn_id"), label
                        ),
                        "thread_key": entry.get("thread_key"),
                        "message_id": message_id,
                        "turn_id": message.get("turn_id"),
                        "labels": [label],
                        "label_evidence": {label: evidence_by_label.get(label) or {}},
                        "confidence": confidence,
                        "expected_review_outcome": row.get(
                            "expected_review_outcome", "supported"
                        ),
                        "public_shadow_case": row.get("public_shadow_case"),
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
            for case in sorted(
                candidates,
                key=lambda item: (
                    -float(item.get("confidence") or 0.0),
                    str(item.get("case_id") or ""),
                ),
            )
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
    for case in sorted(
        candidates,
        key=lambda item: (-float(item.get("confidence") or 0.0), str(item.get("case_id") or "")),
    ):
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
            "unsupported_evidence_labels": [
                "labels whose proposed evidence is missing, generic, or unsupported by the message"
            ],
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


def parse_review_response(response: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    if not response.get("choices"):
        raise ValueError("empty reviewer choices")
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
        for label in parsed.get("unsupported_evidence_labels")
        or parsed.get("evidence_unsupported_labels")
        or []
        if label in proposed
    ]
    missing = [
        label
        for label in labels
        if label in proposed and label not in supported and label not in unsupported
    ]
    unsupported = list(dict.fromkeys([*unsupported, *unsupported_evidence, *missing]))
    supported = [label for label in supported if label not in unsupported]
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "supported_labels": supported,
        "unsupported_labels": unsupported,
        "unsupported_evidence_labels": unsupported_evidence,
        "confidence": max(0.0, min(1.0, confidence)),
        "needs_human_review": bool(parsed.get("needs_human_review")),
    }


def final_review_payload(action: dict[str, Any]) -> dict[str, Any]:
    if any(
        key in action
        for key in ["supported_labels", "unsupported_labels", "unsupported_evidence_labels"]
    ):
        return action
    for key in ["review", "result", "output"]:
        value = action.get(key)
        if isinstance(value, dict):
            return value
    return action


def expected_review_outcome(case: dict[str, Any]) -> str:
    value = str(case.get("expected_review_outcome") or "supported").strip().casefold()
    if value in {"human_review", "needs_human_review"}:
        return "needs_human_review"
    return value if value in {"supported", "unsupported"} else "supported"


def review_passed(case: dict[str, Any], review: dict[str, Any], min_review_confidence: float) -> bool:
    labels = [label for label in case.get("labels") or [] if label in SCOPE_LABEL_ORDER]
    unsupported = set(review.get("unsupported_labels") or [])
    confidence_ok = float(review["confidence"]) >= min_review_confidence
    outcome = expected_review_outcome(case)
    if outcome == "unsupported":
        return bool(labels) and all(label in unsupported for label in labels)
    if outcome == "needs_human_review":
        return bool(labels) and (
            bool(review["needs_human_review"]) or all(label in unsupported for label in labels)
        )
    if review["needs_human_review"]:
        return False
    return confidence_ok and not unsupported


def classify_review_failure(
    exc: BaseException, *, retry_exhausted: bool = False
) -> dict[str, Any]:
    exception_type = type(exc).__name__
    text = f"{exception_type} {exc}".casefold()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        failure_class = "timeout"
        failure_stage = "reviewer_call"
    elif any(token in text for token in ("context length", "maximum context", "prompt too long", "prompt_context", "token limit", "payload too large")):
        failure_class = "prompt_context_issue"
        failure_stage = "prompt_context"
    elif any(token in text for token in ("source_open", "source-open", "clean source", "source ref", "source_refs", "inspect_review_case", "source lookup", "source reopen")):
        failure_class = "source_open_issue"
        failure_stage = "source_open"
    elif any(token in text for token in ("aggregation", "aggregate", "review_buckets", "failure_taxonomy", "per_label", "report row", "summary report")):
        failure_class = "report_aggregation_bug"
        failure_stage = "report_aggregation"
    elif any(token in text for token in ("connection", "transport", "http", "ssl", "rate limit")):
        failure_class = "provider_transport_error"
        failure_stage = "reviewer_call"
    elif isinstance(exc, (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, AttributeError)):
        failure_class = "provider_response_shape"
        failure_stage = "reviewer_response_parse"
    else:
        failure_class = "unexpected_exception"
        failure_stage = "reviewer_call_or_parse"
    failure_classes = [failure_class]
    if retry_exhausted:
        failure_classes.append("retry_exhaustion")
    return {
        "failure_class": failure_class,
        "failure_classes": failure_classes,
        "exception_type": exception_type,
        "failure_stage": failure_stage,
    }


def failure_taxonomy(review_results: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    by_exception_type: dict[str, int] = {}
    retry_exhausted_count = 0
    failure_count = 0
    for item in review_results:
        failure_class = item.get("failure_class")
        if not failure_class:
            continue
        failure_count += 1
        classes = [str(value) for value in item.get("failure_classes") or [failure_class]]
        for key in classes:
            by_class[key] = by_class.get(key, 0) + 1
        exception_type = str(item.get("exception_type") or "unknown")
        by_exception_type[exception_type] = by_exception_type.get(exception_type, 0) + 1
        if item.get("retry_exhausted"):
            retry_exhausted_count += 1
    return {
        "known_classes": REVIEW_FAILURE_CLASSES,
        "by_class": dict(sorted(by_class.items())),
        "by_exception_type": dict(sorted(by_exception_type.items())),
        "retry_exhausted_count": retry_exhausted_count,
        "failure_count": failure_count,
    }


def label_failure_class(
    item: dict[str, Any], label: str, *, min_review_confidence: float = 0.65
) -> str:
    if item.get("failure_class"):
        return "operational_failure"
    shadow_case = str(item.get("public_shadow_case") or "").casefold()
    expected = str(item.get("expected_review_outcome") or "").casefold()
    if (
        "stale" in shadow_case
        or "superseded" in shadow_case
        or "currentness" in shadow_case
        or (expected == "needs_human_review" and label in (item.get("unsupported_labels") or []))
    ):
        return "stale_or_currentness_boundary"
    if label in (item.get("unsupported_evidence_labels") or []):
        return "unsupported_label_evidence"
    if item.get("needs_human_review") or expected == "needs_human_review":
        return "human_review_boundary"
    if label in (item.get("unsupported_labels") or []):
        return "unsupported_label"
    if float(item.get("review_confidence") or 0.0) < float(min_review_confidence):
        return "low_review_confidence"
    return "unsupported_label"


def label_failure_taxonomy(
    review_results: list[dict[str, Any]], *, min_review_confidence: float = 0.65
) -> dict[str, Any]:
    by_label: dict[str, dict[str, Any]] = {}
    by_class: dict[str, int] = {}
    for item in review_results:
        # Public shadow cohorts intentionally contain unsupported and stale
        # cases that may pass because the expected outcome is a safe rejection
        # or human-review boundary. Keep them in this diagnostic taxonomy so a
        # green shadow run still explains which label boundaries were exercised;
        # `ok` and `failed_label_categories` remain the gate signals.
        if item.get("passed") and expected_review_outcome(item) == "supported":
            continue
        labels = [label for label in item.get("labels") or [] if label in SCOPE_LABEL_ORDER]
        if not labels:
            continue
        for label in labels:
            failure_class = label_failure_class(
                item, label, min_review_confidence=min_review_confidence
            )
            by_class[failure_class] = by_class.get(failure_class, 0) + 1
            label_bucket = by_label.setdefault(
                label,
                {
                    "failed_count": 0,
                    "by_class": {},
                    "public_safe_examples": [],
                },
            )
            label_bucket["failed_count"] += 1
            label_bucket["by_class"][failure_class] = (
                label_bucket["by_class"].get(failure_class, 0) + 1
            )
            example = {
                "case_id": str(item.get("case_id") or ""),
                "failure_class": failure_class,
                "expected_review_outcome": expected_review_outcome(item),
            }
            public_shadow_case = str(item.get("public_shadow_case") or "")
            if public_shadow_case:
                example["public_shadow_case"] = public_shadow_case
            label_bucket["public_safe_examples"].append(example)
    for label_bucket in by_label.values():
        label_bucket["by_class"] = dict(sorted(label_bucket["by_class"].items()))
        label_bucket["public_safe_examples"] = sorted(
            label_bucket["public_safe_examples"],
            key=lambda item: (
                str(item.get("failure_class") or ""),
                str(item.get("case_id") or ""),
            ),
        )
    return {
        "known_classes": LABEL_FAILURE_CLASSES,
        "by_label": {label: by_label[label] for label in sorted(by_label)},
        "by_class": dict(sorted(by_class.items())),
        "failure_count": sum(int(item.get("failed_count") or 0) for item in by_label.values()),
    }


def public_shadow_requirements(cases: list[dict[str, Any]]) -> dict[str, bool]:
    present = {str(case.get("public_shadow_case") or "") for case in cases}
    return {key: key in present for key in PUBLIC_SHADOW_REQUIREMENT_KEYS}


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
    review: dict[str, Any] | None = None
    attempt_count = 0
    for attempt_index in range(1, attempts + 1):
        attempt_count = attempt_index
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
            review = parse_review_response(response, list(case.get("labels") or []))
            break
        except Exception as exc:
            last_error = exc
    if response is None or review is None:
        if last_error:
            raise last_error
        raise RuntimeError("reviewer returned no response")
    usage = compact_usage(response.get("usage") or {})
    passed = review_passed(case, review, min_review_confidence)
    return {
        "case_id": case.get("case_id"),
        "prompt_kind": PROMPT_KIND,
        "expected_review_outcome": expected_review_outcome(case),
        "public_shadow_case": case.get("public_shadow_case"),
        "labels": case.get("labels") or [],
        "passed": bool(passed),
        "supported_label_count": len(review["supported_labels"]),
        "unsupported_label_count": len(review["unsupported_labels"]),
        "unsupported_evidence_label_count": len(review["unsupported_evidence_labels"]),
        "unsupported_evidence_labels": review["unsupported_evidence_labels"],
        "needs_human_review": review["needs_human_review"],
        "review_confidence": round(float(review["confidence"]), 4),
        "attempt_count": attempt_count,
        "usage": usage,
        "cache": deepseek_cache_metrics_from_usage(usage),
    }


def agentic_review_messages(
    case: dict[str, Any], *, max_steps: int, min_tool_steps: int
) -> list[dict[str, str]]:
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
                            {"error": "Call inspect_review_case before final."}, ensure_ascii=False
                        ),
                    }
                )
                continue
            review = parse_review_payload(
                final_review_payload(action), list(case.get("labels") or [])
            )
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
    if review is None:
        review = {
            "supported_labels": [],
            "unsupported_labels": [
                label for label in case.get("labels") or [] if label in SCOPE_LABEL_ORDER
            ],
            "unsupported_evidence_labels": [],
            "confidence": 0.0,
            "needs_human_review": True,
        }
    passed = review_passed(case, review, min_review_confidence)
    return {
        "case_id": case.get("case_id"),
        "prompt_kind": PROMPT_KIND,
        "review_mode": "agentic",
        "expected_review_outcome": expected_review_outcome(case),
        "public_shadow_case": case.get("public_shadow_case"),
        "labels": case.get("labels") or [],
        "passed": bool(passed),
        "supported_label_count": len(review["supported_labels"]),
        "unsupported_label_count": len(review["unsupported_labels"]),
        "unsupported_evidence_label_count": len(review["unsupported_evidence_labels"]),
        "unsupported_evidence_labels": review["unsupported_evidence_labels"],
        "needs_human_review": review["needs_human_review"],
        "review_confidence": round(float(review["confidence"]), 4),
        "tool_step_count": tool_step_count,
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
    }


def review_status(
    case_count: int, passed_count: int, *, min_cases: int, min_pass_rate: float
) -> str:
    if case_count < min_cases:
        return "insufficient_selected_cases"
    pass_rate = (passed_count / case_count) if case_count else 0.0
    if pass_rate < min_pass_rate:
        return "insufficient_source_review_pass_rate"
    return "sufficient"


def per_label_case_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in SCOPE_LABEL_ORDER:
        count = sum(1 for case in cases if label in (case.get("labels") or []))
        if count:
            counts[label] = count
    return counts


def per_label_review_floors(
    cases: list[dict[str, Any]], *, min_label_pass_rate: float
) -> dict[str, dict[str, Any]]:
    counts = per_label_case_counts(cases)
    return {
        label: {
            "selected_case_count": int(counts.get(label) or 0),
            "min_selected_cases": 1,
            "min_pass_rate": float(min_label_pass_rate),
            "selection_floor_met": int(counts.get(label) or 0) >= 1,
        }
        for label in SCOPE_LABEL_ORDER
    }


def review_buckets(
    review_results: list[dict[str, Any]], *, selected_case_count: int
) -> dict[str, int]:
    accepted = sum(1 for item in review_results if item.get("passed"))
    model_failure = sum(
        1 for item in review_results if item.get("error") or item.get("failure_class")
    )
    ambiguous_or_human_review = sum(
        1
        for item in review_results
        if not item.get("passed")
        and not item.get("error")
        and not item.get("failure_class")
        and item.get("needs_human_review")
    )
    expected_supported = sum(
        1 for item in review_results if item.get("expected_review_outcome") == "supported"
    )
    expected_unsupported = sum(
        1 for item in review_results if item.get("expected_review_outcome") == "unsupported"
    )
    expected_human_review = sum(
        1
        for item in review_results
        if item.get("expected_review_outcome") == "needs_human_review"
    )
    rejected = max(0, len(review_results) - accepted - ambiguous_or_human_review - model_failure)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "ambiguous_or_human_review": ambiguous_or_human_review,
        "model_failure": model_failure,
        "needs_human_review": ambiguous_or_human_review,
        "unreviewed": max(0, int(selected_case_count) - len(review_results)),
        "expected_supported": expected_supported,
        "expected_unsupported": expected_unsupported,
        "expected_human_review": expected_human_review,
    }


def per_label_review_stats(
    review_results: list[dict[str, Any]], *, min_label_pass_rate: float
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for label in SCOPE_LABEL_ORDER:
        items = [item for item in review_results if label in (item.get("labels") or [])]
        if not items:
            continue
        passed_count = sum(1 for item in items if item.get("passed"))
        pass_rate = passed_count / len(items)
        out[label] = {
            "case_count": len(items),
            "passed_count": passed_count,
            "failed_count": max(0, len(items) - passed_count),
            "pass_rate": round(pass_rate, 4),
            "min_pass_rate": float(min_label_pass_rate),
            "status": "accepted" if pass_rate >= float(min_label_pass_rate) else "below_floor",
        }
    return out


def failed_label_categories(
    per_label: dict[str, dict[str, Any]], *, min_label_pass_rate: float
) -> list[str]:
    return [
        label
        for label, stats in per_label.items()
        if int(stats.get("case_count") or 0) > 0
        and float(stats.get("pass_rate") or 0.0) < min_label_pass_rate
    ]


def source_review_claim_level(
    *,
    public_shadow: bool,
    status: str,
    failures: int,
    case_count: int,
) -> str:
    if status != "sufficient" or failures > 0:
        return "diagnostic_only"
    if public_shadow:
        return "public_shadow_source_review"
    if case_count > 24:
        return "broader_selected_source_review_diagnostic"
    return "selected_semantic_label_source_review"


def cannot_claim(status: str, *, live: bool, claim_level: str = "diagnostic_only") -> list[str]:
    claims = [
        "global_semantic_label_correctness",
        "human_reviewed_label_correctness",
        "semantic_completeness",
    ]
    if not live:
        claims.append("fresh_live_model_review")
    if status != "sufficient":
        claims.append("selected_source_review_passed")
    if claim_level == "broader_selected_source_review_diagnostic":
        claims.append("selected_source_review_green_gate")
    if claim_level == "public_shadow_source_review":
        claims.append("selected_registry_source_review_passed")
    return claims


def run_semantic_scope_source_review(
    *,
    registry_path: str | Path | None = None,
    public_shadow: bool = False,
    live: bool = False,
    api_key_env: str = "AIPPOCAMPUS_DEEPSEEK_API_KEY",
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
    if public_shadow and registry_path:
        raise ValueError("--public-shadow cannot be combined with an explicit registry path")
    resolved_route = resolve_model_route(
        "agentic_source_review"
        if agentic_review and model_route == "default" and not model
        else model_route,
        explicit_model=model,
    )
    registry = (
        Path(registry_path).resolve()
        if registry_path
        else PUBLIC_SHADOW_REGISTRY.resolve()
        if public_shadow
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    cases = selected_review_cases(registry, max_cases=max_cases)
    cohort = "public_source_review_shadow" if public_shadow else "selected_registry_source_review"
    shadow_requirements = public_shadow_requirements(cases) if public_shadow else {}
    shadow_ready = not public_shadow or all(shadow_requirements.values())
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
        status = "observe_only" if shadow_ready else "public_shadow_missing_required_cases"
        return {
            "ok": len(cases) >= min_cases and shadow_ready,
            "status": status,
            "cohort": cohort,
            "claim_level": "diagnostic_only",
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/readiness/stage-0-5-readiness.md"
            ),
            "cannot_claim": cannot_claim(status, live=False),
            "live_model_used": False,
            "case_count": len(cases),
            "passed_count": 0,
            "pass_rate": 0.0,
            "min_cases": int(min_cases),
            "min_pass_rate": float(min_pass_rate),
            "per_label": {},
            "per_label_floors": per_label_review_floors(
                cases, min_label_pass_rate=min_label_pass_rate
            ),
            "review_buckets": review_buckets([], selected_case_count=len(cases)),
            "failed_label_categories": [],
            "min_label_pass_rate": float(min_label_pass_rate),
            "label_coverage": sorted(
                {label for case in cases for label in case.get("labels") or []}
            ),
            "model_route": resolved_route.as_dict(),
            "cases": [],
            "failure_taxonomy": failure_taxonomy([]),
            "label_failure_taxonomy": label_failure_taxonomy([]),
            "public_shadow_requirements": shadow_requirements,
            "privacy_boundary": privacy_boundary,
        }
    api_key = os.environ.get(api_key_env)
    if not api_key:
        status = "live_model_missing_api_key"
        return {
            "ok": False,
            "status": status,
            "cohort": cohort,
            "claim_level": "blocked_live_model",
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/readiness/stage-0-5-readiness.md"
            ),
            "cannot_claim": cannot_claim(status, live=True),
            "live_model_used": False,
            "case_count": len(cases),
            "passed_count": 0,
            "pass_rate": 0.0,
            "min_cases": int(min_cases),
            "min_pass_rate": float(min_pass_rate),
            "per_label": {},
            "per_label_floors": per_label_review_floors(
                cases, min_label_pass_rate=min_label_pass_rate
            ),
            "review_buckets": review_buckets([], selected_case_count=len(cases)),
            "failed_label_categories": [],
            "min_label_pass_rate": float(min_label_pass_rate),
            "label_coverage": sorted(
                {label for case in cases for label in case.get("labels") or []}
            ),
            "model_route": resolved_route.as_dict(),
            "cases": [],
            "failure_taxonomy": failure_taxonomy([]),
            "label_failure_taxonomy": label_failure_taxonomy([]),
            "public_shadow_requirements": shadow_requirements,
            "privacy_boundary": privacy_boundary,
        }

    review_results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    failures = 0
    reviewer = chat_fn or call_chat_json
    max_workers = min(max(1, int(concurrency)), max(1, len(cases)))

    def failed_case(case: dict[str, Any], exc: BaseException) -> dict[str, Any]:
        retry_exhausted = not agentic_review
        classified = classify_review_failure(exc, retry_exhausted=retry_exhausted)
        return {
            "case_id": case.get("case_id"),
            "prompt_kind": PROMPT_KIND,
            "expected_review_outcome": expected_review_outcome(case),
            "public_shadow_case": case.get("public_shadow_case"),
            "labels": case.get("labels") or [],
            "passed": False,
            "supported_label_count": 0,
            "unsupported_label_count": len(case.get("labels") or []),
            "unsupported_evidence_label_count": 0,
            "unsupported_evidence_labels": [],
            "needs_human_review": True,
            "review_confidence": 0.0,
            "error": "redacted_review_failure",
            **classified,
            "retry_exhausted": retry_exhausted,
            "attempt_count": max(1, int(max_attempts)) if not agentic_review else None,
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
    status = review_status(
        len(cases), passed_count, min_cases=min_cases, min_pass_rate=min_pass_rate
    )
    final_status = (
        "live_model_partial_failure"
        if failures
        else "public_shadow_missing_required_cases"
        if not shadow_ready
        else status
    )
    pass_rate = round((passed_count / len(cases)) if cases else 0.0, 4)
    per_label = per_label_review_stats(
        review_results, min_label_pass_rate=min_label_pass_rate
    )
    claim_level = source_review_claim_level(
        public_shadow=public_shadow,
        status=final_status,
        failures=failures,
        case_count=len(cases),
    )
    return {
        "ok": status == "sufficient" and failures == 0 and shadow_ready,
        "status": final_status,
        "cohort": cohort,
        "claim_level": claim_level,
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/readiness/stage-0-5-readiness.md"
        ),
        "cannot_claim": cannot_claim(final_status, live=True, claim_level=claim_level),
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
        "failure_taxonomy": failure_taxonomy(review_results),
        "label_failure_taxonomy": label_failure_taxonomy(
            review_results, min_review_confidence=min_review_confidence
        ),
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
        "per_label": per_label,
        "per_label_floors": per_label_review_floors(
            cases, min_label_pass_rate=min_label_pass_rate
        ),
        "review_buckets": review_buckets(review_results, selected_case_count=len(cases)),
        "failed_label_categories": failed_label_categories(
            per_label, min_label_pass_rate=min_label_pass_rate
        ),
        "cases": review_results,
        "public_shadow_requirements": shadow_requirements,
        "privacy_boundary": privacy_boundary,
        "boundary": "DeepSeek-compatible review checks selected sidecar labels against clean source; it is not human review or global correctness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument(
        "--public-shadow",
        action="store_true",
        help="Use the checked-in public-safe source-review shadow cohort.",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--api-key-env", default="AIPPOCAMPUS_DEEPSEEK_API_KEY")
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
    if args.public_shadow and args.registry:
        parser.error("--public-shadow cannot be combined with --registry")
    result = run_semantic_scope_source_review(
        registry_path=args.registry,
        public_shadow=args.public_shadow,
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
        print(
            f"cases: {result.get('case_count')} passed: {result.get('passed_count')} pass_rate: {result.get('pass_rate')}"
        )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
