#!/usr/bin/env python3
"""AIppocampus subconscious consolidation worker.

This is the cheap-LLM background layer: it reads clean project-timeline turns,
asks a fast model to propose concept edges, and writes source-backed staging
JSONL. The staging file is intentionally not truth; `build_concept_graph.py`
decides how much of it to admit into the local concept graph.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    cli_public_error_object,
    compact_text,
    now_utc,
    sanitize_external_model_payload,
)
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    ChatClientConfig,
    chat_json,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_base_url,
    flash_model,
    resolve_model_route,
    route_artifact_source,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.subconscious.edge_validation import (
    ALLOWED_EDGE_TYPES,  # noqa: F401 - re-exported for direct-script compatibility
    WORKER_EDGE_POLICY,
    clamp_confidence,  # noqa: F401 - re-exported for direct-script compatibility
    validate_source_backed_edges,
)
from aippocampus_runtime.subconscious.staging_maintenance import (
    StagingPressureThresholds,
    queue_pressure,
)

PROMPT_VERSION = "aippocampus-subconscious-v0"
DEFAULT_MODEL = flash_model()
DEFAULT_BASE_URL = deepseek_base_url()
DEFAULT_MAX_TURNS = 48


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
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
    if "hit_rate" in cache:
        result["hit_rate"] = public_float(cache.get("hit_rate"))
    return result


def public_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, Mapping):
        return {}
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {key: public_count(usage.get(key)) for key in keys if key in usage}


def public_error(error: Any) -> dict[str, str] | None:
    if not isinstance(error, Mapping):
        return None
    return cli_public_error_object(error)


def public_staging_pressure(pressure: Any) -> dict[str, Any]:
    if not isinstance(pressure, Mapping):
        return {}
    return {
        "file_name": str(pressure.get("file_name") or ""),
        "row_count": public_count(pressure.get("row_count")),
        "byte_count": public_count(pressure.get("byte_count")),
        "warning": bool(pressure.get("warning")),
        "warning_reasons": [
            str(reason) for reason in pressure.get("warning_reasons") or [] if str(reason)
        ],
        "pressure_level": str(pressure.get("pressure_level") or "ok"),
    }


def public_worker_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "dry_run": bool(result.get("dry_run")),
        "turn_count": public_count(result.get("turn_count")),
        "edge_count": public_count(result.get("edge_count")),
        "wrote": bool(result.get("wrote")),
        "cache": public_cache(result.get("cache")),
        "usage": public_usage(result.get("usage")),
        "model_route": public_model_route(result.get("model_route")),
        "staging_pressure": public_staging_pressure(result.get("staging_pressure")),
        "output_private_artifact": bool(result.get("output")),
        "output_boundary": "worker_details_are_local_private_artifacts",
    }
    error = public_error(result.get("error"))
    if error:
        payload["error"] = error
    return payload


SYSTEM_PROMPT = """You are AIppocampus subconscious consolidation.
Extract source-backed concept memory edges from clean conversation turns.
Return only JSON. Do not summarize the conversation.

Rules:
- Use only concepts present or strongly implied by the provided turns.
- Prefer durable concepts, aliases, project decisions, libraries, workflows, and contrasts.
- Do not invent facts or source references.
- Do not include secrets, local file paths, API keys, or long quotes.
- Keep labels short and reusable.
- Every edge must include at least one source_ref from the provided turn ids.
- Output schema:
{
  "concepts": [{"label": "...", "kind": "project|library|workflow|decision|topic|person|artifact", "confidence": 0.0}],
  "edges": [
    {
      "src": "...",
      "dst": "...",
      "edge_type": "alias|same_decision_space|project_topic|decision_about|depends_on|contrasts_with|supersedes|related",
      "confidence": 0.0,
      "why": "short reason",
      "source_refs": [{"turn_ref": "t0"}]
    }
  ]
}
"""


def default_project_timeline_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "project_timeline.json"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "project_timeline.json"


def default_staging_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "subconscious_edges.jsonl"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "subconscious_edges.jsonl"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def select_timeline_turns(
    timeline: dict[str, Any],
    *,
    project: str | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    project_filter = (project or "").casefold().strip()
    for project_data in (timeline.get("projects") or {}).values():
        if not isinstance(project_data, dict):
            continue
        label = str(project_data.get("project_label") or "")
        tags = " ".join(str(item) for item in project_data.get("project_tags") or [])
        if project_filter and project_filter not in (label + " " + tags).casefold():
            continue
        for turn in project_data.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            rows.append(
                {
                    "turn_ref": f"t{len(rows)}",
                    "thread_key": turn.get("thread_key"),
                    "title": turn.get("title"),
                    "project_label": turn.get("project_label") or label,
                    "timestamp": turn.get("timestamp"),
                    "turn_id": turn.get("turn_id"),
                    "turn_index": turn.get("turn_index"),
                    "user_line": turn.get("user_line"),
                    "assistant_line": turn.get("assistant_line"),
                    "topic_terms": unique_preserve(
                        [str(item) for item in turn.get("topic_terms") or []], limit=16
                    ),
                    "scope_labels": unique_preserve(
                        [str(item) for item in turn.get("scope_labels") or []], limit=12
                    ),
                    "semantic_scope_labels": unique_preserve(
                        [str(item) for item in turn.get("semantic_scope_labels") or []], limit=12
                    ),
                    "source_refs": [
                        {
                            "thread_key": ref.get("thread_key"),
                            "message_id": ref.get("message_id"),
                            "turn_id": ref.get("turn_id"),
                            "source_line": ref.get("source_line"),
                            "role": ref.get("role"),
                            "phase": ref.get("phase") or "",
                        }
                        for ref in turn.get("source_refs") or []
                        if isinstance(ref, dict)
                    ][:8],
                    "user": compact_text(str(turn.get("user") or ""), 420),
                    "assistant": compact_text(str(turn.get("assistant") or ""), 760),
                }
            )
    rows.sort(
        key=lambda item: (str(item.get("timestamp") or ""), int(item.get("turn_index") or 0)),
        reverse=True,
    )
    if int(max_turns) > 0:
        rows = rows[: max(1, int(max_turns))]
    for idx, row in enumerate(rows):
        row["turn_ref"] = f"t{idx}"
    return rows


def user_prompt_for_turns(turns: list[dict[str, Any]]) -> str:
    # Keep the stable task tag before source turns so broad runs over different
    # source slices still share a small but useful DeepSeek prefix.
    payload = {
        "prompt_version": PROMPT_VERSION,
        "task": "propose_source_backed_concept_edges",
        "turns": turns,
    }
    payload = sanitize_external_model_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def call_deepseek(
    *,
    api_key: str,
    model: str,
    base_url: str,
    turns: list[dict[str, Any]],
    max_tokens: int | None,
    timeout: int,
    service_name: str = "DeepSeek API",
    response_format_json: bool = True,
) -> dict[str, Any]:
    return chat_json(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_for_turns(turns)},
        ],
        ChatClientConfig(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=0,
            service_name=service_name,
            response_format_json=response_format_json,
            cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
        ),
    )


def parse_model_json(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("model response has no choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        finish_reason = choices[0].get("finish_reason")
        usage = response.get("usage") or {}
        raise ValueError(
            "model response content is empty; "
            f"finish_reason={finish_reason!r}, completion_tokens={usage.get('completion_tokens')!r}. "
            "If --max-tokens was passed, remove or increase it."
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model response is not valid JSON: {content[:240]}") from exc
    return parsed if isinstance(parsed, dict) else {}


def validate_edges(parsed: dict[str, Any], turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ref = {str(turn.get("turn_ref")): turn for turn in turns}

    def worker_source_ref(turn_ref: str, turn: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "turn_ref": turn_ref,
            "thread_key": turn.get("thread_key"),
            "title": turn.get("title"),
            "project_label": turn.get("project_label"),
            "turn_index": turn.get("turn_index"),
            "user_line": turn.get("user_line"),
            "assistant_line": turn.get("assistant_line"),
            "timestamp": turn.get("timestamp"),
        }

    return validate_source_backed_edges(
        parsed,
        by_ref,
        policy=WORKER_EDGE_POLICY,
        project_source_ref=worker_source_ref,
    )


def append_staging_edges(
    path: Path,
    edges: list[dict[str, Any]],
    *,
    model: str,
    batch_id: str,
    usage: dict[str, Any] | None = None,
    prompt_version: str = PROMPT_VERSION,
    source: str = "deepseek_subconscious",
    model_route: dict[str, Any] | None = None,
    pressure_thresholds: StagingPressureThresholds | None = None,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for edge in edges:
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_edge",
                "created_at": now_utc(),
                "prompt_version": prompt_version,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": public_model_route(model_route),
                "usage": usage or {},
                **edge,
            }
            # The edge JSONL is a local-private review queue, not a public graph.
            # Keep source refs for auditability, but redact model-returned prose
            # before it can persist secrets or machine-local paths.
            safe_event = sanitize_external_model_payload(event)
            fh.write(json.dumps(safe_event, ensure_ascii=False) + "\n")
    pressure = queue_pressure(path, thresholds=pressure_thresholds)
    return {"staging_pressure": pressure}


def run_worker(
    *,
    timeline_path: Path,
    output_path: Path,
    project: str | None,
    max_turns: int,
    model: str,
    base_url: str,
    api_key: str | None,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    model_route: str | None = None,
    max_tokens: int | None = None,
    timeout: int = 60,
    dry_run: bool = False,
    no_write: bool = False,
) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
    batch_id = f"subconscious-{int(time.time())}"
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "timeline": str(timeline_path),
            "output": str(output_path),
            "turn_count": len(turns),
            "prompt_preview": compact_text(user_prompt_for_turns(turns), 1800),
        }
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
    artifact_source = route_artifact_source(route, "subconscious")
    key_value = api_key or os.environ.get(resolved_api_key_env)
    if not key_value:
        raise RuntimeError(
            f"missing {route_service_name(route)} key; "
            f"set {resolved_api_key_env} or pass --api-key-env"
        )
    response = call_deepseek(
        api_key=str(key_value),
        model=resolved_model,
        base_url=resolved_base_url,
        turns=turns,
        max_tokens=max_tokens,
        timeout=timeout,
        service_name=route_service_name(route),
        response_format_json=bool(capabilities.supports_json_response if capabilities else True),
    )
    parsed = parse_model_json(response)
    edges = validate_edges(parsed, turns)
    usage = response.get("usage") or {}
    staging_pressure: dict[str, Any] = {}
    if not no_write:
        write_result = append_staging_edges(
            output_path,
            edges,
            model=resolved_model,
            batch_id=batch_id,
            usage=usage,
            source=artifact_source,
            model_route=route_payload,
        )
        staging_pressure = write_result.get("staging_pressure") or {}
    return {
        "ok": True,
        "dry_run": False,
        "model": resolved_model,
        "model_route": route_payload,
        "timeline": str(timeline_path),
        "output": str(output_path),
        "turn_count": len(turns),
        "edge_count": len(edges),
        "edges": edges,
        "timeout": timeout,
        "usage": usage,
        "cache": route_cache_metrics(route, usage),
        "wrote": False if no_write else True,
        "batch_id": batch_id,
        "staging_pressure": staging_pressure,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--timeline")
    parser.add_argument("--output")
    parser.add_argument("--project")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional manual output cap. By default the worker does not send max_tokens.",
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument(
        "--include-prompt-preview",
        action="store_true",
        help="Print the private dry-run prompt preview for local debugging.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    timeline_path = (
        Path(args.timeline).resolve()
        if args.timeline
        else default_project_timeline_path(registry_path=registry_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_staging_path(registry_path=registry_path)
    )
    try:
        result = run_worker(
            timeline_path=timeline_path,
            output_path=output_path,
            project=args.project,
            max_turns=args.max_turns,
            model=args.model,
            base_url=args.base_url,
            api_key=None,
            api_key_env=args.api_key_env,
            model_route=args.model_route,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            dry_run=args.dry_run,
            no_write=args.no_write,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(public_worker_payload(result), ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if args.json_output:
        print(json.dumps(public_worker_payload(result), ensure_ascii=False, indent=2))
    else:
        if result.get("dry_run"):
            print(f"dry run: {result['turn_count']} turn(s)")
            if args.include_prompt_preview:
                print(result["prompt_preview"])
        else:
            print(f"subconscious edges: {result['edge_count']}")
            if result.get("output"):
                print("output: <local-private-artifact>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
