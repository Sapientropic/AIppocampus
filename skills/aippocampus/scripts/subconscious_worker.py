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
from typing import Any

from aippocampuslib import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    sanitize_external_model_payload,
)
from build_concept_graph import concept_is_noise
from deepseek_model_routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_base_url,
    flash_model,
    resolve_model_route,
    route_artifact_source,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from model_client import DEEPSEEK_PREFIX_CACHE_CONTRACT, ChatClientConfig, chat_json
from registry import registry_paths, unique_preserve

PROMPT_VERSION = "aippocampus-subconscious-v0"
DEFAULT_MODEL = flash_model()
DEFAULT_BASE_URL = deepseek_base_url()
DEFAULT_MAX_TURNS = 48

ALLOWED_EDGE_TYPES = {
    "alias",
    "same_decision_space",
    "project_topic",
    "decision_about",
    "depends_on",
    "contrasts_with",
    "supersedes",
    "related",
}

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


def clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def validate_edges(parsed: dict[str, Any], turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ref = {str(turn.get("turn_ref")): turn for turn in turns}
    out: list[dict[str, Any]] = []
    for edge in parsed.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("src") or "").strip()
        dst = str(edge.get("dst") or "").strip()
        edge_type = str(edge.get("edge_type") or "related").strip()
        confidence = clamp_confidence(edge.get("confidence"))
        if edge_type not in ALLOWED_EDGE_TYPES:
            edge_type = "related"
        if not src or not dst or src.casefold() == dst.casefold():
            continue
        if concept_is_noise(src) or concept_is_noise(dst):
            continue
        refs: list[dict[str, Any]] = []
        for ref in edge.get("source_refs") or []:
            if not isinstance(ref, dict):
                continue
            turn_ref = str(ref.get("turn_ref") or "")
            turn = by_ref.get(turn_ref)
            if not turn:
                continue
            refs.append(
                {
                    "turn_ref": turn_ref,
                    "thread_key": turn.get("thread_key"),
                    "title": turn.get("title"),
                    "project_label": turn.get("project_label"),
                    "turn_index": turn.get("turn_index"),
                    "user_line": turn.get("user_line"),
                    "assistant_line": turn.get("assistant_line"),
                    "timestamp": turn.get("timestamp"),
                }
            )
        if not refs or confidence < 0.45:
            continue
        out.append(
            {
                "src": src,
                "dst": dst,
                "edge_type": edge_type,
                "confidence": round(confidence, 4),
                "why": compact_text(str(edge.get("why") or ""), 220),
                "source_refs": refs[:3],
            }
        )
    return out


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
) -> None:
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
                "model_route": model_route or {},
                "usage": usage or {},
                **edge,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


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
    if not no_write:
        append_staging_edges(
            output_path,
            edges,
            model=resolved_model,
            batch_id=batch_id,
            usage=usage,
            source=artifact_source,
            model_route=route_payload,
        )
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("dry_run"):
            print(f"dry run: {result['turn_count']} turn(s)")
            print(result["prompt_preview"])
        else:
            print(f"subconscious edges: {result['edge_count']}")
            print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
