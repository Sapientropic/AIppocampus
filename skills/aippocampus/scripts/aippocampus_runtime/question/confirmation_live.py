#!/usr/bin/env python3
"""Optional live/model confirmer for borderline question-pair requests.

This adapter consumes `question_pair_confirmation_request` JSONL produced by
`question_tracking.py --pending-confirmations-output` and writes explicit
confirmation artifacts that `question_tracking.py --borderline-confirmations`
can consume. It is opt-in: by default the CLI performs a dry-run and never calls
an external model.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    NO_PROVIDER_CACHE_CONTRACT,
    ChatClientConfig,
    chat_json,
)
from aippocampus_runtime.model.routing import (
    resolve_model_route,
    route_cache_metrics,
    route_service_name,
)
from aippocampus_runtime.question.confirmation import (
    append_confirmation_artifacts,
    default_confirmation_artifacts_path,
    default_confirmation_requests_path,
    iter_confirmation_jsonl,
)
from aippocampus_runtime.question.tracking import default_jobs_path

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-question-confirmation-live-v1"
REQUEST_KIND = "question_pair_confirmation_request"
ARTIFACT_KIND = "question_pair_confirmation_artifact"

ChatFn = Callable[[list[dict[str, str]], ChatClientConfig], Mapping[str, Any]]


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_model_route(route: Any) -> dict[str, str]:
    if not isinstance(route, Mapping):
        return {}
    provider = str(route.get("provider") or "").strip()
    if not provider:
        return {}
    safe = "".join(char for char in provider[:48] if char.isalnum() or char in {"_", "-", "."})
    return {"provider": safe or "unknown"}


def public_usage_count(usage: Any) -> int:
    if not isinstance(usage, list):
        return 0
    return len([item for item in usage if isinstance(item, Mapping)])


def public_confirmation_live_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(payload.get("ok")),
        "status": str(payload.get("status") or "unknown"),
        "request_count": public_count(payload.get("request_count")),
        "artifact_count": public_count(
            payload.get("artifact_count")
            if payload.get("artifact_count") is not None
            else len(payload.get("artifacts") or [])
        ),
        "wrote_count": public_count(payload.get("wrote_count")),
        "raw_text_emitted": bool(payload.get("raw_text_emitted")),
        "can_claim": [
            str(item)
            for item in payload.get("can_claim") or []
            if str(item) == "live_model_confirmation_artifacts_generated"
        ],
        "cannot_claim": [
            str(item)
            for item in payload.get("cannot_claim") or []
            if str(item)
            in {
                "live_external_model_confirmation",
                "real_user_calibration",
                "user_visible_recall_improvement",
            }
        ],
        "usage_count": public_usage_count(payload.get("usage")),
        "model_route": public_model_route(payload.get("route")),
        "output_boundary": "confirmation_details_are_local_private_artifacts",
    }


def valid_request(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("kind") or "") == REQUEST_KIND
        and bool(str(row.get("pair_id") or ""))
        and len([value for value in row.get("source_finding_ids") or [] if str(value)]) == 2
    )


def load_confirmation_requests(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for row in iter_confirmation_jsonl(path):
        if not valid_request(row):
            continue
        requests.append(row)
        if limit is not None and len(requests) >= limit:
            break
    return requests


def request_prompt_messages(request: Mapping[str, Any]) -> list[dict[str, str]]:
    contract = {
        "task": "Accept or reject whether two already source-backed extracted questions should be linked.",
        "allowed_decisions": ["accept", "reject"],
        "allowed_link_types": ["recurring", "evolving", "parent_of", "child_of", "related"],
        "source_of_truth_boundary": (
            "The model may only judge the compact request. It must not invent source evidence "
            "and must not replace original source refs."
        ),
        "output_schema": {
            "decision": "accept|reject",
            "confidence": "number between 0 and 1",
            "link_type": "recurring|evolving|parent_of|child_of|related",
            "rationale": "short reason, no quotes or private source text",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a conservative AIppocampus question-link reviewer. "
                "Return one JSON object only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"contract": contract, "request": request},
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _response_content(response: Mapping[str, Any]) -> str:
    if "decision" in response or "action" in response:
        return json.dumps(dict(response), ensure_ascii=False)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if isinstance(message, Mapping):
        return str(message.get("content") or "")
    return str(first.get("text") or "")


def parse_model_confirmation(response: Mapping[str, Any]) -> dict[str, Any]:
    content = _response_content(response).strip()
    if not content:
        return {"decision": "invalid", "confidence": 0.0, "invalid_reason": "empty_model_response"}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"decision": "invalid", "confidence": 0.0, "invalid_reason": "non_json_model_response"}
    if not isinstance(parsed, Mapping):
        return {"decision": "invalid", "confidence": 0.0, "invalid_reason": "non_object_model_response"}
    decision = str(parsed.get("decision") or parsed.get("action") or "").strip().casefold()
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return {"decision": "invalid", "confidence": 0.0, "invalid_reason": "malformed_confidence"}
    if decision not in {"accept", "reject"}:
        return {
            "decision": "invalid",
            "confidence": confidence,
            "invalid_reason": "unsupported_decision",
        }
    link_type = str(parsed.get("link_type") or "related").strip()
    if link_type not in {"recurring", "evolving", "parent_of", "child_of", "related"}:
        link_type = "related"
    return {
        "decision": decision,
        "confidence": round(confidence, 4),
        "link_type": link_type,
        "rationale": compact_text(str(parsed.get("rationale") or parsed.get("reason") or ""), 260),
    }


def confirmation_artifact(
    request: Mapping[str, Any],
    parsed: Mapping[str, Any],
    *,
    model: str,
    provider: str,
) -> dict[str, Any]:
    decision = str(parsed.get("decision") or "invalid")
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "pair_id": str(request.get("pair_id") or ""),
        "source_finding_ids": [
            str(value) for value in request.get("source_finding_ids") or [] if str(value)
        ],
        "decision": decision,
        "confidence": float(parsed.get("confidence") or 0.0),
        "link_type": str(parsed.get("link_type") or "related"),
        "model": compact_text(model, 120),
        "source": compact_text(f"{provider}_question_confirmation", 120),
        "rationale": compact_text(str(parsed.get("rationale") or ""), 260),
        "created_at": now_utc(),
        "prompt_version": PROMPT_VERSION,
        "request_contract": request.get("privacy_contract") or {},
    }
    if parsed.get("invalid_reason"):
        artifact["invalid_reason"] = compact_text(str(parsed.get("invalid_reason") or ""), 120)
    return artifact


def _cache_contract_for_provider(provider: str) -> str:
    return DEEPSEEK_PREFIX_CACHE_CONTRACT if provider == "deepseek" else NO_PROVIDER_CACHE_CONTRACT


def run_question_confirmation_live(
    *,
    requests_path: Path,
    output_path: Path,
    route_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    call_model: bool = False,
    no_write: bool = False,
    max_requests: int | None = None,
    timeout: float = 60.0,
    chat_fn: ChatFn = chat_json,
) -> dict[str, Any]:
    requests = load_confirmation_requests(requests_path, limit=max_requests)
    route = resolve_model_route(
        route_name,
        explicit_model=model,
        explicit_base_url=base_url,
        explicit_api_key_env=api_key_env,
    )
    effective_api_key_env = api_key_env or route.api_key_env
    api_key = os.environ.get(effective_api_key_env)
    if not call_model:
        return {
            "ok": True,
            "status": "dry_run_no_model_call",
            "request_count": len(requests),
            "wrote_count": 0,
            "output": str(output_path),
            "route": route.as_dict(),
            "api_key_env": effective_api_key_env,
            "raw_text_emitted": False,
            "cannot_claim": ["live_external_model_confirmation"],
        }
    if not api_key:
        return {
            "ok": True,
            "status": "skipped_missing_api_key",
            "request_count": len(requests),
            "wrote_count": 0,
            "output": str(output_path),
            "route": route.as_dict(),
            "api_key_env": effective_api_key_env,
            "raw_text_emitted": False,
            "cannot_claim": ["live_external_model_confirmation"],
        }
    config = ChatClientConfig(
        api_key=api_key,
        model=model or route.model,
        base_url=base_url or route.base_url,
        timeout=timeout,
        service_name=route_service_name(route),
        response_format_json=True,
        cache_contract=_cache_contract_for_provider(route.provider),
    )
    artifacts: list[dict[str, Any]] = []
    usage: list[dict[str, Any]] = []
    for request in requests:
        response = chat_fn(request_prompt_messages(request), config)
        parsed = parse_model_confirmation(response)
        artifacts.append(
            confirmation_artifact(
                request,
                parsed,
                model=config.model,
                provider=route.provider,
            )
        )
        usage.append(route_cache_metrics(route, dict(response.get("usage") or {})))
    wrote_count = 0 if no_write else append_confirmation_artifacts(output_path, artifacts)
    return {
        "ok": True,
        "status": "live_model_confirmation_completed",
        "request_count": len(requests),
        "artifact_count": len(artifacts),
        "wrote_count": wrote_count,
        "output": str(output_path),
        "route": route.as_dict(),
        "api_key_env": effective_api_key_env,
        "usage": usage,
        "artifacts": artifacts if no_write else [],
        "raw_text_emitted": False,
        "can_claim": ["live_model_confirmation_artifacts_generated"],
        "cannot_claim": ["real_user_calibration", "user_visible_recall_improvement"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--requests")
    parser.add_argument("--output")
    parser.add_argument("--route")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else default_jobs_path(args.registry, args.registry_dir)
    )
    requests_path = (
        Path(args.requests).resolve()
        if args.requests
        else default_confirmation_requests_path(jobs_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_confirmation_artifacts_path(jobs_path)
    )
    payload = run_question_confirmation_live(
        requests_path=requests_path,
        output_path=output_path,
        route_name=args.route,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        call_model=args.call_model,
        no_write=args.no_write,
        max_requests=args.max_requests,
        timeout=args.timeout,
    )
    if args.json_output:
        print(json.dumps(public_confirmation_live_payload(payload), ensure_ascii=False, indent=2))
    else:
        print(
            "question confirmation live: "
            f"{payload.get('status')} "
            f"({payload.get('wrote_count', 0)} written)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
