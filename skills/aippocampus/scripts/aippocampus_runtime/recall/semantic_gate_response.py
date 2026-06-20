"""Response and diagnostic stage for the semantic recall gate.

This helper is intentionally static: it owns worker response parsing, public
projection, and unavailable/fail-open result shaping without introducing a
middleware registry. Keep model output here as routing evidence only; clean
source reopen remains the boundary for source-backed facts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.recall.semantic_result_cache import CACHE_TELEMETRY_KEYS
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.subconscious.runtime import call_chat_json
from aippocampus_runtime.subconscious.worker import clamp_confidence, parse_model_json

PROMPT_VERSION = "aippocampus-semantic-recall-gate-v0"
SCHEMA_VERSION = 1

VALID_DECISIONS = {"skip", "background_only", "scent", "evidence"}
DECISION_RANK = {"skip": 0, "background_only": 1, "scent": 2, "evidence": 3}
HIGH_RISK_MAX_DECISION = "scent"

ChatFn = Callable[..., dict[str, Any]]


SYSTEM_PROMPT = """You are AIppocampus semantic recall gate.
Your job is to decide whether a user's current prompt should receive ambient
old-thread memory hints, and to generate multilingual aliases for local memory
retrieval.

Rules:
- Be conservative. Ordinary coding/product tasks usually return skip or background_only.
- Use scent when prior conversation memory may help but is not requested as proof.
- Use evidence only when the user asks for exact prior wording, last reply, source-backed status, or a decision that depends on old-thread facts.
- Do not invent facts. Do not answer the user. Do not quote source text.
- Query aliases are search hints only; they are not claims.
- Prefer cross-lingual and paraphrase aliases when useful.
- Avoid over-personalizing generic work prompts.
- Return JSON only.
"""


def sanitize_prompt_for_semantic_gate(
    prompt: str,
    *,
    project_root: Path | str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Redact likely credentials before sending prompt text to a semantic model.

    The prompt hook is automatic, so credential handling must be stricter than a
    normal chat completion. Still, many useful prompts mention a token or
    connection string while asking a memory question. We redact known secret
    shapes and only hard-block prompts that are private-key dumps or mostly
    credentials after redaction.
    """

    return sanitize_external_model_text(prompt, project_root=project_root)


def prompt_may_contain_secret(prompt: str) -> bool:
    _, policy = sanitize_prompt_for_semantic_gate(prompt)
    return bool(policy.get("redacted") or policy.get("hard_block"))


def normalize_alias(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return ""
    if len(text) > 96:
        return ""
    if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", text):
        return ""
    if prompt_may_contain_secret(text):
        return ""
    return text


def collect_aliases(values: list[Any], limit: int = 24) -> list[str]:
    aliases: list[str] = []
    for value in values:
        if isinstance(value, list):
            aliases.extend(collect_aliases(value, limit=limit))
            continue
        text = normalize_alias(value)
        if text:
            aliases.append(text)
            aliases.extend(split_query_terms([text])[:4])
    return unique_preserve(aliases, limit=limit)


def collect_exact_aliases(values: list[Any], limit: int = 24) -> list[str]:
    return unique_preserve([text for value in values if (text := normalize_alias(value))], limit)


def worker_prompt(worker: str, payload: dict[str, Any]) -> str:
    schema = {
        "worker": worker,
        "decision": "skip|background_only|scent|evidence",
        "intent": "ordinary_task|recall|continuation|decision_check|preference_update|implementation",
        "confidence": 0.0,
        "query_aliases": ["short multilingual search aliases"],
        "memory_scope": ["current_project|registered_threads|cross_project|working_memory"],
        "negative_contexts": ["when not to recall"],
        "anti_personalization_risk": "low|medium|high",
        "reason": "short reason",
    }
    task = {
        "gate": "Decide whether ambient memory should surface. Be strict about skip vs scent.",
        "alias": "Generate multilingual/paraphrase query aliases for local retrieval. Do not decide facts.",
        "scope": "Choose memory scope and detect over-personalization risk.",
    }.get(worker, "Analyze semantic recall relevance.")
    # Put the shared payload first. The worker-specific task/schema are smaller
    # and intentionally trail the common prefix so parallel workers can reuse
    # DeepSeek's server-side prefix cache whenever it has landed.
    return json.dumps(
        {
            "input": payload,
            "output_schema": schema,
            "task": task,
        },
        ensure_ascii=False,
        indent=2,
    )


def parse_worker_response(response: dict[str, Any], worker: str) -> dict[str, Any]:
    parsed = parse_model_json(response)
    decision = str(parsed.get("decision") or "skip").strip().casefold()
    if decision not in VALID_DECISIONS:
        decision = "skip"
    aliases = collect_aliases(
        [
            parsed.get("query_aliases") or [],
            parsed.get("aliases") or [],
            parsed.get("concept_aliases") or [],
        ]
    )
    scopes = unique_preserve(
        [str(x) for x in parsed.get("memory_scope") or [] if str(x).strip()], limit=8
    )
    negatives = unique_preserve(
        [str(x) for x in parsed.get("negative_contexts") or [] if str(x).strip()], limit=8
    )
    risk = str(parsed.get("anti_personalization_risk") or "medium").strip().casefold()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    return {
        "worker": worker,
        "decision": decision,
        "intent": str(parsed.get("intent") or "").strip()[:80],
        "confidence": clamp_confidence(parsed.get("confidence")),
        "query_aliases": aliases,
        "memory_scope": scopes,
        "negative_contexts": negatives,
        "anti_personalization_risk": risk,
        "reason": compact_text(str(parsed.get("reason") or ""), 220),
    }


def run_worker(
    worker: str,
    *,
    payload: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    timeout: float,
    temperature: float,
    chat_fn: ChatFn,
    service_name: str = "DeepSeek API",
    response_format_json: bool = True,
) -> dict[str, Any]:
    args = (
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": worker_prompt(worker, payload)},
        ],
        api_key,
        model,
        base_url,
        None,
        timeout,
        temperature,
    )
    if chat_fn is call_chat_json:
        response = chat_fn(
            *args,
            service_name=service_name,
            response_format_json=response_format_json,
        )
    else:
        response = chat_fn(*args)
    parsed = parse_worker_response(response, worker)
    parsed["usage"] = response.get("usage") or {}
    return parsed


def error_bucket(message: str) -> str:
    text = str(message or "").casefold()
    if "overall deadline" in text:
        return "overall_deadline"
    if "timeout" in text or "timed out" in text:
        return "read_timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "invalid_json"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "connect" in text or "connection" in text or "urlerror" in text:
        return "connection_error"
    return "semantic_worker_error"


def error_buckets(errors: list[str]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for error in errors:
        kind = error_bucket(error)
        buckets[kind] = buckets.get(kind, 0) + 1
    return buckets


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def public_model_route(route: Any) -> dict[str, str]:
    if not isinstance(route, Mapping):
        return {}
    provider = str(route.get("provider") or "").strip()
    safe = "".join(char for char in provider[:48] if char.isalnum() or char in {"_", "-", "."})
    return {"provider": safe or "unknown"}


def public_cache(cache: Any) -> dict[str, Any]:
    if not isinstance(cache, Mapping):
        return {}
    result: dict[str, Any] = {"available": bool(cache.get("available"))}
    for key in ("hit_tokens", "miss_tokens"):
        if key in cache:
            result[key] = public_count(cache.get(key))
    return result


def public_cache_diagnostics(diagnostics: Any) -> dict[str, Any]:
    if not isinstance(diagnostics, Mapping):
        return {}
    result: dict[str, Any] = {}
    lookup = str(diagnostics.get("lookup") or "")
    if lookup in {"disabled", "hit", "miss", "expired", "write_error"}:
        result["lookup"] = lookup
    cache_key = str(diagnostics.get("cache_key") or "")
    if re.fullmatch(r"sg_[0-9a-f]{24}", cache_key):
        result["cache_key"] = cache_key
    if "semantic_cues_in_cache_key" in diagnostics:
        result["semantic_cues_in_cache_key"] = bool(diagnostics.get("semantic_cues_in_cache_key"))
    telemetry = diagnostics.get("telemetry")
    if isinstance(telemetry, Mapping):
        result["telemetry"] = {
            str(key): public_count(value)
            for key, value in telemetry.items()
            if str(key) in CACHE_TELEMETRY_KEYS
        }
    return result


def public_error_buckets(buckets: Any) -> dict[str, int]:
    if not isinstance(buckets, Mapping):
        return {}
    allowed = {
        "auth_error",
        "foreground_budget",
        "read_timeout",
        "overall_deadline",
        "semantic_worker_error",
    }
    return {
        str(key): public_count(value)
        for key, value in buckets.items()
        if str(key) in allowed
    }


def public_float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def public_semantic_budget(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    allowed_reasons = {
        "foreground_post_semantic_reserve",
        "worker_socket_timeout_policy",
    }
    allowed_policies = {"worker_socket_timeout_half_of_overall_deadline"}
    allowed_actions = {
        "increase_max_elapsed_ms_or_use_background_recall",
        "no_budget_change_needed",
    }
    result: dict[str, Any] = {
        "requested_timeout": public_float(value.get("requested_timeout")),
        "effective_timeout": public_float(value.get("effective_timeout")),
        "overall_deadline_seconds": public_float(value.get("overall_deadline_seconds")),
        "max_elapsed_ms": public_float(value.get("max_elapsed_ms")),
        "budget_clipped": bool(value.get("budget_clipped")),
    }
    policy = str(value.get("effective_timeout_policy") or "")
    if policy in allowed_policies:
        result["effective_timeout_policy"] = policy
    reason = str(value.get("budget_clip_reason") or "")
    if reason in allowed_reasons:
        result["budget_clip_reason"] = reason
    action = str(value.get("next_step_hint") or "")
    if action in allowed_actions:
        result["next_step_hint"] = action
    return {key: item for key, item in result.items() if item is not None}


def public_partial_failure_reasons(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    allowed = {
        "auth_error",
        "foreground_budget",
        "read_timeout",
        "overall_deadline",
        "semantic_worker_error",
    }
    return [str(item) for item in value if str(item) in allowed]


def public_semantic_gate_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    workers_value = result.get("workers")
    workers = workers_value if isinstance(workers_value, list) else []
    return {
        "available": bool(result.get("available")),
        "decision": str(result.get("decision") or "skip")
        if str(result.get("decision") or "skip") in VALID_DECISIONS
        else "skip",
        "confidence": public_confidence(result.get("confidence")),
        "cached": bool(result.get("cached")),
        "availability_reason": str(result.get("availability_reason") or "")
        if result.get("availability_reason")
        else None,
        "diagnostic": str(result.get("diagnostic") or "") if result.get("diagnostic") else None,
        "error_buckets": public_error_buckets(result.get("error_buckets")),
        "worker_count": public_count(result.get("worker_count") or len(workers)),
        "successful_worker_count": public_count(result.get("successful_worker_count")),
        "failed_worker_count": public_count(result.get("failed_worker_count")),
        "partial_success": bool(result.get("partial_success")),
        "partial_failure_reasons": public_partial_failure_reasons(
            result.get("partial_failure_reasons")
        ),
        "budget": public_semantic_budget(result.get("budget")),
        "cache": public_cache(result.get("cache")),
        "cache_diagnostics": public_cache_diagnostics(result.get("cache_diagnostics")),
        "model_route": public_model_route(result.get("model_route")),
        "elapsed_ms": public_count(result.get("elapsed_ms")),
        "output_boundary": "semantic_gate_private_worker_details_omitted",
    }


def unavailable_result(
    reason: str,
    *,
    elapsed_ms: float = 0.0,
    model_route: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    cache_diagnostics: dict[str, Any] | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    worker_count: int | None = None,
) -> dict[str, Any]:
    buckets = error_buckets([reason])
    if buckets.get("read_timeout"):
        availability_reason = "semantic_worker_timeout"
        diagnostic = "semantic_provider_read_timeout"
    elif buckets.get("auth_error"):
        availability_reason = "semantic_unavailable"
        diagnostic = "semantic_disabled_or_auth_unavailable"
    else:
        availability_reason = "semantic_unavailable"
        diagnostic = "semantic_unavailable"
    return {
        "kind": "aippocampus_semantic_recall_gate",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "availability_reason": availability_reason,
        "diagnostic": diagnostic,
        "query_aliases": [],
        "memory_scope": [],
        "negative_contexts": [],
        "anti_personalization_risk": "medium",
        "reasons": [reason],
        "workers": [],
        "errors": [reason],
        "error_buckets": buckets,
        "timeout": timeout,
        "temperature": temperature,
        "worker_count": worker_count,
        "cache": cache or {},
        "model_route": model_route or {},
        "cache_diagnostics": cache_diagnostics or {},
        "secret_policy": None,
        "cached": False,
        "elapsed_ms": round(elapsed_ms, 2),
    }


def foreground_budget_unavailable_result(
    reason: str,
    *,
    diagnostic: str,
    deadline_seconds: float | None,
    elapsed_ms: float = 0.0,
    model_route: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    cache_diagnostics: dict[str, Any] | None = None,
    timeout: float | None = None,
    temperature: float | None = None,
    worker_count: int | None = None,
) -> dict[str, Any]:
    result = unavailable_result(
        reason,
        elapsed_ms=elapsed_ms,
        model_route=model_route,
        cache=cache,
        cache_diagnostics=cache_diagnostics,
        timeout=timeout,
        temperature=temperature,
        worker_count=worker_count,
    )
    result.update(
        {
            "availability_reason": "foreground_budget_skipped",
            "diagnostic": diagnostic,
            "error_buckets": {"foreground_budget": 1},
            "deadline": {
                "seconds": deadline_seconds,
                "exceeded": True,
                "unfinished_workers": [],
            },
            "foreground": True,
        }
    )
    return result
