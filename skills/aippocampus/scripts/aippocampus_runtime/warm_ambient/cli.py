"""CLI edge for warm ambient recall."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.model.routing import DEFAULT_DEEPSEEK_API_KEY_ENV
from aippocampus_runtime.recall.ambient_cards import count_cards_by_field
from aippocampus_runtime.subconscious.worker import DEFAULT_BASE_URL, DEFAULT_MODEL
from aippocampus_runtime.warm_ambient import recall, scheduler
from aippocampus_runtime.warm_ambient.config import warm_recall_config_from_env

PUBLIC_STATUSES = {
    "disabled",
    "guard_coverage_incomplete",
    "not_scheduled",
    "queued",
    "quorum_not_met",
    "ready",
    "scheduled",
    "skipped",
    "skipped_missing_api_key",
    "suppressed",
    "timeout",
    "unavailable",
    "withheld",
    "written",
}
PUBLIC_REASONS = {
    "",
    "all_scouts_observed",
    "background warm recall is not enabled",
    "empty prompt",
    "empty prompt after sanitization",
    "foreground hook must not wait for warm scouts",
    "guard_coverage_incomplete",
    "missing api key",
    "missing thread id",
    "no_scouts",
    "quorum_and_guard_coverage_met",
    "timeout",
}
PUBLIC_SUPPRESSION_BUCKETS = {
    "current_thread_echo",
    "evidence_sentinel_blocked",
    "guard_coverage_incomplete",
    "no_supported_cards",
    "privacy_blocked",
    "privacy_boundary",
    "quorum_not_met",
    "source_validation_failed",
    "topic_epoch_suppressed",
}
PUBLIC_SOURCE_VALIDATION_STATUSES = {
    "missing_source_ref",
    "missing_source_refs",
    "supported",
    "unsupported",
    "unverified_no_source_index",
}
PUBLIC_SCOUT_ERROR_KINDS = {
    "empty_response",
    "exception",
    "invalid_json",
    "invalid_schema",
    "read_timeout",
    "timeout",
    "unknown",
}
PUBLIC_PROVENANCE_CLASSES = {
    "cached_warm_card",
    "cognitive_map_route",
    "deterministic_cue",
    "source_backed_reopen",
    "warm_scout_proposal",
    "working_memory_model",
    "working_memory_source",
}
PUBLIC_SUPPORT_LEVELS = {"scent", "candidate", "evidence"}


def _public_status(value: object) -> str:
    text = str(value or "").strip()
    return text if text in PUBLIC_STATUSES else "unknown"


def _public_reason(value: object) -> str:
    text = str(value or "").strip()
    return text if text in PUBLIC_REASONS else ""


def _public_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def _public_float(value: object) -> float:
    try:
        return max(0.0, float(str(value or "0.0")))
    except (TypeError, ValueError):
        return 0.0


def _public_bool(value: object) -> bool:
    return bool(value)


def _public_bucket_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    buckets: list[str] = []
    for item in value:
        bucket = str(item or "").strip()
        if bucket in PUBLIC_SUPPRESSION_BUCKETS and bucket not in buckets:
            buckets.append(bucket)
    return buckets


def _public_count_map(value: object, allowed: set[str]) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, count in value.items():
        name = str(key or "").strip()
        if name in allowed:
            counts[name] = _public_int(count)
    return counts


def _card_count(result: Mapping[str, Any]) -> int:
    cards = result.get("cards")
    return len(cards) if isinstance(cards, list) else _public_int(result.get("card_count"))


def _card_count_map(result: Mapping[str, Any], field: str, allowed: set[str]) -> dict[str, int]:
    cards = result.get("cards")
    if not isinstance(cards, list):
        return {}
    return _public_count_map(count_cards_by_field(cards, field), allowed)


def _public_cache(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    cache: dict[str, Any] = {
        "available": _public_bool(value.get("available")),
        "hit_tokens": _public_int(value.get("hit_tokens")),
        "miss_tokens": _public_int(value.get("miss_tokens")),
        "hit_rate": _public_float(value.get("hit_rate")),
    }
    kind = str(value.get("kind") or "").strip()
    if kind in {"deepseek_prefix", "generic", "none"}:
        cache["kind"] = kind
    return cache


def _public_cache_write(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    status = _public_status(value.get("status"))
    summary: dict[str, Any] = {
        "status": status,
        "reason": _public_reason(value.get("reason")),
        "card_count": _public_int(value.get("card_count")),
        "source_ref_fingerprint_count": _public_int(
            value.get("source_ref_fingerprint_count")
        ),
    }
    guard_coverage = _public_guard_coverage(value.get("guard_coverage"))
    if guard_coverage:
        summary["guard_coverage"] = guard_coverage
    residue = value.get("residue_export")
    if isinstance(residue, Mapping):
        summary["residue_export"] = {
            "status": _public_status(residue.get("status")),
            "residue_count": _public_int(residue.get("residue_count")),
        }
    return summary


def _public_guard_coverage(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    families: dict[str, Any] = {}
    raw_families = value.get("families")
    if isinstance(raw_families, Mapping):
        for family, details in raw_families.items():
            name = str(family or "").strip()
            if name not in {"privacy_boundary_guard", "evidence_gap_sentinel"}:
                continue
            if not isinstance(details, Mapping):
                continue
            state = str(details.get("state") or "").strip()
            if state not in {"resolved", "blocked", "missing", "timed_out", "not_requested"}:
                state = "missing"
            family_payload: dict[str, Any] = {
                "state": state,
                "selected_lane_count": _public_int(details.get("selected_lane_count")),
                "observed_lane_count": _public_int(details.get("observed_lane_count")),
            }
            error_kinds = _public_count_map(
                details.get("error_kinds"), PUBLIC_SCOUT_ERROR_KINDS
            )
            if error_kinds:
                family_payload["error_kinds"] = error_kinds
            families[name] = family_payload
    status = str(value.get("status") or "").strip()
    if status not in {"complete", "incomplete", "not_requested"}:
        status = "incomplete" if families else "not_requested"
    return {
        "status": status,
        "satisfied": _public_bool(value.get("satisfied")),
        "requested_families": [
            str(item)
            for item in value.get("requested_families") or []
            if str(item) in {"privacy_boundary_guard", "evidence_gap_sentinel"}
        ],
        "blocked_families": [
            str(item)
            for item in value.get("blocked_families") or []
            if str(item) in {"privacy_boundary_guard", "evidence_gap_sentinel"}
        ],
        "incomplete_families": [
            str(item)
            for item in value.get("incomplete_families") or []
            if str(item) in {"privacy_boundary_guard", "evidence_gap_sentinel"}
        ],
        "families": families,
    }


def _public_diagnostics(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    diagnostics: dict[str, Any] = {
        "reason_buckets": _public_bucket_list(value.get("reason_buckets")),
        "card_count": _public_int(value.get("card_count")),
        "quorum_met": _public_bool(value.get("quorum_met")),
        "current_thread_echo_count": _public_int(value.get("current_thread_echo_count")),
    }
    source_counts = _public_count_map(
        value.get("source_validation_status_counts"),
        PUBLIC_SOURCE_VALIDATION_STATUSES,
    )
    if source_counts:
        diagnostics["source_validation_status_counts"] = source_counts
    topic_epoch_action = str(value.get("topic_epoch_action") or "").strip()
    if topic_epoch_action in {"fallback", "reuse", "rotate", "suppress"}:
        diagnostics["topic_epoch_action"] = topic_epoch_action
    guard_coverage = _public_guard_coverage(value.get("guard_coverage"))
    if guard_coverage:
        diagnostics["guard_coverage"] = guard_coverage
    return diagnostics


def _public_cli_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    cache_write = _public_cache_write(result.get("cache_write"))
    payload: dict[str, Any] = {
        "kind": "aippocampus_warm_ambient_recall",
        "schema_version": _public_int(result.get("schema_version")),
        "prompt_version": recall.PROMPT_VERSION,
        "ok": _public_bool(result.get("ok")),
        "available": _public_bool(result.get("available")),
        "status": _public_status(result.get("status")),
        "reason": _public_reason(result.get("reason")),
        "quorum_met": _public_bool(result.get("quorum_met")),
        "useful_signal_quorum_met": _public_bool(result.get("useful_signal_quorum_met")),
        "batch_end_reason": _public_reason(result.get("batch_end_reason")),
        "scout_count": _public_int(result.get("scout_count")),
        "observed_scout_result_count": _public_int(
            result.get("observed_scout_result_count")
            or len(result.get("scouts") or [])
        ),
        "max_workers": _public_int(result.get("max_workers")),
        "prefix_cache_warmup_scout_count": _public_int(
            result.get("prefix_cache_warmup_scout_count")
        ),
        "accepted_scout_count": _public_int(result.get("accepted_scout_count")),
        "failed_scout_count": _public_int(result.get("failed_scout_count")),
        "trace_fallback_card_count": _public_int(result.get("trace_fallback_card_count")),
        "card_count": _card_count(result),
        "provenance_counts": _card_count_map(
            result, "provenance_class", PUBLIC_PROVENANCE_CLASSES
        ),
        "support_level_counts": _card_count_map(
            result, "support_level", PUBLIC_SUPPORT_LEVELS
        ),
        "current_thread_echo_count": _public_int(result.get("current_thread_echo_count")),
        "scout_error_kinds": _public_count_map(
            result.get("scout_error_kinds"),
            PUBLIC_SCOUT_ERROR_KINDS,
        ),
        "suppression_reason_buckets": _public_bucket_list(
            result.get("suppression_reason_buckets")
        ),
        "suppression_diagnostics": _public_diagnostics(
            result.get("suppression_diagnostics")
        ),
        "guard_coverage": _public_guard_coverage(result.get("guard_coverage")),
        "cache": _public_cache(result.get("cache")),
        "cache_write": cache_write,
        "elapsed_ms": _public_float(result.get("elapsed_ms")),
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_prompt_trace_emitted": False,
            "raw_scouts_emitted": False,
            "raw_cards_emitted": False,
            "model_route_emitted": False,
            "user_id_emitted": False,
        },
    }
    if cache_write is None:
        payload.pop("cache_write")
    return payload


def _status_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus warm status")
    parser.add_argument(
        "--cwd",
        help="Accepted for CLI consistency; warm status is registry/job-dir scoped.",
    )
    parser.add_argument("--job-dir")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--strict-exit-code",
        action="store_true",
        help="Return non-zero when the optional warm queue is blocked.",
    )
    args = parser.parse_args(list(argv))
    job_dir = (
        Path(args.job_dir)
        if args.job_dir
        else scheduler.default_warm_job_dir(
            registry_path=args.registry,
            registry_dir=args.registry_dir,
        )
    )
    payload = scheduler.warm_status_payload(job_dir=job_dir)
    if args.json_output:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        activity = payload.get("job_activity") or {}
        print("AIppocampus warm ambient")
        print(f"status: {payload.get('status')}")
        print(f"ordinary recall: {'usable' if payload.get('ordinary_recall_usable') else 'degraded'}")
        print(
            "jobs: "
            f"pending={activity.get('pending_recent_count', 0)}, "
            f"stale={activity.get('pending_stale_count', 0)}, "
            f"completed={activity.get('completed_count', 0)}"
        )
        print(f"worker: {activity.get('worker_evidence')}")
        print(f"next: {payload.get('action_code')}")
        action = payload.get("foreground_action") if isinstance(payload, dict) else None
        if isinstance(action, dict):
            print(f"action: {action.get('command')}")
        else:
            print(f"action: {payload.get('next_command')}")
        print("boundary: optional background warming; first recall and search do not wait for it")
    if args.strict_exit_code and not payload.get("ok"):
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0] == "status":
        return _status_main(raw_args[1:])

    parser = argparse.ArgumentParser(
        prog="aippocampus warm",
        usage="aippocampus warm status [--json] | aippocampus warm --prompt <cue> [operator options]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Warm ambient recall is optional background warming.

Safe foreground check:
  aippocampus warm status
  aippocampus warm status --json

`warm status` does not make model calls. It tells you whether optional warm
workers are usable, blocked, or unconfigured. Ordinary source-backed
`aippocampus search` and `aippocampus agent recall` remain usable when warm
ambient is off.

If blocked or unconfigured: leave warm ambient off, or configure the provider
key only if you intentionally want optional background warming. Worker/scout
flags below are operator controls for explicit warm jobs, not prerequisites for
first recall.""",
    )
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
    parser.add_argument("--reasoning-effort", choices=["high", "max", "provider"], default=None)
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
    args = parser.parse_args(raw_args)

    if args.job_file:
        summary = recall.run_warm_job_file(args.job_file)
        public_summary = _public_cli_payload(summary)
        if args.json_output:
            json.dump(public_summary, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            print("warm ambient recall job complete")
        return 0 if summary.get("ok") else 2
    if not args.prompt:
        parser.error("--prompt is required unless --job-file is provided")

    cli_config = warm_recall_config_from_env().with_overrides(
        timeout=args.timeout,
        temperature=args.temperature,
        thinking=args.thinking,
        reasoning_effort=args.reasoning_effort,
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
    public_result = _public_cli_payload(result)
    if args.json_output:
        json.dump(public_result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        if not result.get("available"):
            print("warm ambient recall unavailable")
        else:
            print("warm ambient recall complete")
    return 2 if args.strict and not result.get("available") else 0


if __name__ == "__main__":
    raise SystemExit(main())
