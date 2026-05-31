"""CLI edge for warm ambient recall."""

from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from aippocampus_runtime.model.routing import DEFAULT_DEEPSEEK_API_KEY_ENV
from aippocampus_runtime.subconscious.worker import DEFAULT_BASE_URL, DEFAULT_MODEL
from aippocampus_runtime.warm_ambient import recall
from aippocampus_runtime.warm_ambient.config import warm_recall_config_from_env


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt")
    parser.add_argument("--job-file")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--thread-id")
    parser.add_argument("--current-thread-key")
    parser.add_argument("--allow-current-thread-echo", action="store_true")
    parser.add_argument(
        "--prompt-trace-json",
        help="Optional sanitized prompt trace JSON array for warm calibration.",
    )
    parser.add_argument("--topic-epoch")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cache")
    parser.add_argument("--residue")
    parser.add_argument("--residue-reason", default="warm_scout")
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--user-id", help="Optional DeepSeek user_id; omit to send a stable sanitized hash.")
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--thinking", choices=["enabled", "disabled", "provider"], default=None)
    parser.add_argument("--quorum", type=int, default=None)
    parser.add_argument("--max-cards", type=int, default=None)
    parser.add_argument("--max-catalog-items", type=int, default=None)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--prefix-cache-warmup-scouts", type=int, default=None)
    parser.add_argument("--prefix-cache-warmup-delay", type=float, default=None)
    parser.add_argument("--wait-all", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.job_file:
        summary = recall.run_warm_job_file(args.job_file)
        if args.json_output:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(
                "warm ambient recall job: "
                f"status={summary.get('status')} "
                f"scout_results={summary.get('observed_scout_result_count', 0)}"
            )
        return 0 if summary.get("ok") else 2
    if not args.prompt:
        parser.error("--prompt is required unless --job-file is provided")

    cli_config = warm_recall_config_from_env().with_overrides(
        timeout=args.timeout,
        temperature=args.temperature,
        thinking=args.thinking,
        quorum=args.quorum,
        max_cards=args.max_cards,
        max_catalog_items=args.max_catalog_items,
        max_workers=args.max_workers,
        prefix_cache_warmup_scouts=args.prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=args.prefix_cache_warmup_delay,
    )
    result = recall.run_warm_ambient_recall(
        args.prompt,
        cwd=args.cwd,
        thread_id=args.thread_id,
        current_thread_key=args.current_thread_key,
        allow_current_thread_echo=args.allow_current_thread_echo,
        prompt_trace=json.loads(args.prompt_trace_json) if args.prompt_trace_json else None,
        topic_epoch=args.topic_epoch,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        cache_path=args.cache,
        residue_path=args.residue,
        residue_reason=args.residue_reason,
        api_key=None,
        api_key_env=args.api_key_env,
        user_id=args.user_id,
        model_route=args.model_route,
        model=args.model,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        config=cli_config,
        wait_all=args.wait_all,
        no_write=args.no_write,
    )
    if args.strict and not result.get("available"):
        result["ok"] = False
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result.get("available"):
            print(f"warm ambient recall unavailable: {result.get('reason') or result.get('status')}")
        else:
            print(
                "warm ambient recall: "
                f"{result.get('accepted_scout_count')} scout(s), "
                f"{len(result.get('cards') or [])} card(s), "
                f"status={result.get('status')}"
            )
    return 2 if args.strict and not result.get("available") else 0


if __name__ == "__main__":
    raise SystemExit(main())
