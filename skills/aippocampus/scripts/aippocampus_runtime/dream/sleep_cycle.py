#!/usr/bin/env python3
"""Detached sleep-cycle runner for ready dream queue items.

This is the execution bridge between deterministic queue planning and bounded
model-backed dream workers. It intentionally stays outside foreground hooks:
ready packs can run only through the detached scheduler path, writes are
serialized by the caller's scheduler lock, and the default mode is no-write so
new dream hypotheses remain projected results until a background operator
explicitly enables staging writes.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.dream import input_pack as dream_input_pack
from aippocampus_runtime.dream import precision_policy as dream_precision_policy
from aippocampus_runtime.dream import queue as dream_queue
from aippocampus_runtime.dream import worker as dream_worker
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    NO_PROVIDER_CACHE_CONTRACT,
    ChatClientConfig,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_base_url,
    flash_model,
    resolve_model_route,
    route_service_name,
)
from aippocampuslib import cli_error_payload, cli_exit_code_for_error_code, compact_text, now_utc

SLEEP_CYCLE_KIND = "aippocampus_dream_sleep_cycle"
SUMMARY_KIND = "aippocampus_dream_sleep_cycle_summary"
QUEUE_ITEM_KIND = dream_queue.QUEUE_ITEM_KIND
RUNNABLE_STATUSES = {"queued", "ready", "ready_for_dream_worker"}
DEFAULT_MAX_ITEMS = 1
DEFAULT_MAX_SAMPLES = 1
DEFAULT_TIMEOUT_SECONDS = 180.0
DEFAULT_WRITE_LOCK_STALE_SECONDS = 10 * 60
REGISTRY_SEED_FILES = (
    "subconscious_jobs.jsonl",
    "promotion_candidates.jsonl",
    "working_memory.jsonl",
    "correction_events.jsonl",
    "agency_affordances.jsonl",
    "coding_decision_events.jsonl",
    "subconscious_edges.jsonl",
)


class FileLock:
    def __init__(self, path: Path, *, stale_seconds: int = DEFAULT_WRITE_LOCK_STALE_SECONDS) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = 0
            if age <= self.stale_seconds:
                raise RuntimeError("dream sleep-cycle writes already locked")
            try:
                self.path.unlink()
            except OSError:
                pass
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, json.dumps({"pid": os.getpid(), "created_at": now_utc()}).encode("utf-8"))
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except OSError:
            pass


def iter_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def append_jsonl(path: Path | None, rows: Iterable[Mapping[str, Any]]) -> int:
    if path is None:
        return 0
    materialized = [dict(row) for row in rows]
    if not materialized:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in materialized:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(materialized)


def write_json(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_utc(value: object) -> Any:
    return dream_queue.parse_utc(str(value or ""))


def format_utc(value: Any) -> str:
    return dream_queue.format_utc(value)


def normalize_now(now: str | Any | None) -> Any:
    return dream_queue.normalize_now(now)


def queue_item_sort_key(item: Mapping[str, Any]) -> tuple[int, str, str, str]:
    return (
        -int(item.get("priority") or 0),
        str(item.get("review_after") or ""),
        str(item.get("prompt_prefix_group") or ""),
        str(item.get("queue_item_id") or ""),
    )


def select_runnable_queue_items(
    queue_items: Iterable[Mapping[str, Any]],
    *,
    now: str | Any | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    run_ready: bool = False,
) -> list[dict[str, Any]]:
    """Select ready or due queue items without widening foreground eligibility."""

    now_dt = normalize_now(now)
    selected: list[dict[str, Any]] = []
    seen_dedup: set[str] = set()
    for raw in sorted((item for item in queue_items if isinstance(item, Mapping)), key=queue_item_sort_key):
        item = dict(raw)
        if item.get("kind") != QUEUE_ITEM_KIND:
            continue
        if str(item.get("status") or "") not in RUNNABLE_STATUSES:
            continue
        if item.get("execution_mode") != dream_queue.EXECUTION_MODE:
            continue
        if item.get("foreground_eligible") is not False:
            continue
        expires_at = parse_utc(item.get("expires_at"))
        if expires_at and expires_at <= now_dt:
            continue
        review_after = parse_utc(item.get("review_after"))
        if not run_ready and review_after and review_after > now_dt:
            continue
        dedup_key = str(item.get("dedup_key") or "")
        if dedup_key and dedup_key in seen_dedup:
            continue
        if dedup_key:
            seen_dedup.add(dedup_key)
        selected.append(item)
        if len(selected) >= max(0, int(max_items)):
            break
    return selected


def packs_by_id(packs: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for pack in packs:
        if not isinstance(pack, Mapping):
            continue
        pack_id = str(pack.get("pack_id") or "")
        if pack_id:
            by_id[pack_id] = dict(pack)
    return by_id


def queue_status_for_worker(worker_run: Mapping[str, Any]) -> str:
    status = str(worker_run.get("status") or "")
    if status == "candidate_parked":
        return "parked"
    if status in {"worker_error", "pack_missing", "model_output_rejected", "skipped_pack_not_ready"}:
        return "failed"
    return "completed"


def queue_lifecycle_row(
    item: Mapping[str, Any],
    *,
    status: str,
    now: str | Any | None,
    worker_run: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    worker_counts = dict((worker_run or {}).get("counts") or {})
    return {
        "schema_version": 1,
        "kind": QUEUE_ITEM_KIND,
        "queue_item_id": item.get("queue_item_id"),
        "created_at": format_utc(normalize_now(now)),
        "status": status,
        "pack_id": item.get("pack_id"),
        "dream_function": item.get("dream_function"),
        "trigger_family": item.get("trigger_family"),
        "dedup_key": item.get("dedup_key"),
        "expires_at": item.get("expires_at"),
        "execution_mode": dream_queue.EXECUTION_MODE,
        "foreground_eligible": False,
        "worker_status": (worker_run or {}).get("status"),
        "worker_counts": worker_counts,
        "error": dict(error or {}) if error else None,
    }


def worker_error_run(item: Mapping[str, Any], exc: BaseException, *, now: str | Any | None) -> dict[str, Any]:
    return {
        "schema_version": dream_worker.SCHEMA_VERSION,
        "kind": dream_worker.WORKER_KIND,
        "created_at": format_utc(normalize_now(now)),
        "status": "worker_error",
        "pack_id": item.get("pack_id"),
        "dream_function": item.get("dream_function"),
        "execution_mode": dream_queue.EXECUTION_MODE,
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "findings": [],
        "adjudicated_findings": [],
        "dream_working_memory_rows": [],
        "rejected_candidates": [],
        "counts": {"findings": 0, "accepted": 0, "parked": 0, "rejected": 0},
        "error": {
            "type": exc.__class__.__name__,
            "message": compact_text(str(exc), 240),
        },
        "no_write": True,
    }


def pack_missing_run(item: Mapping[str, Any], *, now: str | Any | None) -> dict[str, Any]:
    return {
        "schema_version": dream_worker.SCHEMA_VERSION,
        "kind": dream_worker.WORKER_KIND,
        "created_at": format_utc(normalize_now(now)),
        "status": "pack_missing",
        "pack_id": item.get("pack_id"),
        "dream_function": item.get("dream_function"),
        "execution_mode": dream_queue.EXECUTION_MODE,
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "findings": [],
        "adjudicated_findings": [],
        "dream_working_memory_rows": [],
        "rejected_candidates": [],
        "counts": {"findings": 0, "accepted": 0, "parked": 0, "rejected": 0},
        "error": {"type": "PackMissing", "message": "queue item pack_id was not found"},
        "no_write": True,
    }


def aggregate_cache(worker_runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    hit = 0
    miss = 0
    available = False
    kinds: set[str] = set()
    for run in worker_runs:
        cache = run.get("cache") or {}
        if not isinstance(cache, Mapping):
            continue
        if cache.get("kind"):
            kinds.add(str(cache.get("kind")))
        available = available or bool(cache.get("available"))
        hit += int(cache.get("hit_tokens") or 0)
        miss += int(cache.get("miss_tokens") or 0)
    total = hit + miss
    return {
        "available": available,
        "kinds": sorted(kinds),
        "hit_tokens": hit,
        "miss_tokens": miss,
        "hit_rate": round(hit / total, 4) if total else None,
    }


def failure_buckets(worker_runs: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for run in worker_runs:
        status = str(run.get("status") or "")
        if status == "worker_error":
            error = run.get("error") or {}
            error_type = str(error.get("type") or "worker_error") if isinstance(error, Mapping) else "worker_error"
            buckets[f"worker_error:{error_type}"] += 1
        elif status in {"pack_missing", "model_output_rejected", "skipped_pack_not_ready"}:
            buckets[status] += 1
    return dict(sorted(buckets.items()))


def attach_retention_policies(
    findings: Iterable[Mapping[str, Any]],
    *,
    structural_voices: Iterable[Mapping[str, Any]] | None = None,
    now: str | Any | None = None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        item = dict(finding)
        item["retention_policy"] = dream_precision_policy.retention_policy_for_probe(
            item,
            structural_voices=structural_voices,
            now=now,
        )
        enriched.append(item)
    return enriched


def write_lock_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None:
            return path.parent / "dream_sleep_cycle_write.lock"
    return None


def run_sleep_cycle(
    packs: Iterable[Mapping[str, Any]],
    *,
    previous_items: Iterable[Mapping[str, Any]] | None = None,
    existing_findings: Iterable[Mapping[str, Any]] | None = None,
    now: str | Any | None = None,
    config: ChatClientConfig | None = None,
    model_call: dream_worker.ModelCall = dream_worker.chat_json,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    no_write: bool = True,
    write_working_memory: bool = True,
    run_ready: bool = False,
    queue_output_path: Path | None = None,
    findings_output_path: Path | None = None,
    working_memory_output_path: Path | None = None,
) -> dict[str, Any]:
    materialized_packs = [dict(pack) for pack in packs if isinstance(pack, Mapping)]
    queue_payload = dream_queue.build_dream_queue(
        materialized_packs,
        previous_items=previous_items or [],
        existing_findings=existing_findings or [],
        now=now,
        max_items=max(1, int(max_items) * 4),
    )
    selected = select_runnable_queue_items(
        queue_payload.get("items") or [],
        now=now,
        max_items=max_items,
        run_ready=run_ready,
    )
    pack_lookup = packs_by_id(materialized_packs)
    worker_runs: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    adjudicated_findings: list[dict[str, Any]] = []
    working_rows: list[dict[str, Any]] = []

    for item in selected:
        pack = pack_lookup.get(str(item.get("pack_id") or ""))
        if not pack:
            run = pack_missing_run(item, now=now)
        else:
            if config is None:
                raise ValueError("config is required when runnable dream queue items are selected")
            try:
                run = dream_worker.run_model_backed_dream_worker(
                    pack,
                    dream_function=str(item.get("dream_function") or ""),
                    config=config,
                    model_call=model_call,
                    max_samples=max_samples,
                    no_write=no_write,
                )
            except Exception as exc:
                run = worker_error_run(item, exc, now=now)
        run = dict(run)
        run["adjudicated_findings"] = attach_retention_policies(
            run.get("adjudicated_findings") or [],
            structural_voices=run.get("findings") or [],
            now=now,
        )
        worker_runs.append(run)
        lifecycle_rows.append(
            queue_lifecycle_row(
                item,
                status=queue_status_for_worker(run),
                now=now,
                worker_run=run,
                error=run.get("error") if isinstance(run.get("error"), Mapping) else None,
            )
        )
        adjudicated_findings.extend(
            item
            for item in run.get("adjudicated_findings") or []
            if isinstance(item, dict)
        )
        working_rows.extend(
            item
            for item in run.get("dream_working_memory_rows") or []
            if isinstance(item, dict)
        )

    written = {"queue": 0, "findings": 0, "working_memory": 0}
    if not no_write:
        active_working_memory_output = working_memory_output_path if write_working_memory else None
        lock_path = write_lock_path(
            queue_output_path, findings_output_path, active_working_memory_output
        )
        # The detached scheduler already serializes project runs. This local
        # lock protects direct `dream_sleep_cycle.py --write` CLI use on
        # Windows, where append-only JSONL writes from separate processes can
        # otherwise interleave without a shared flock primitive.
        if lock_path:
            with FileLock(lock_path):
                written["queue"] = append_jsonl(queue_output_path, lifecycle_rows)
                written["findings"] = append_jsonl(findings_output_path, adjudicated_findings)
                written["working_memory"] = append_jsonl(
                    active_working_memory_output, working_rows
                )
        else:
            written["queue"] = append_jsonl(queue_output_path, lifecycle_rows)
            written["findings"] = append_jsonl(findings_output_path, adjudicated_findings)
            written["working_memory"] = append_jsonl(
                active_working_memory_output, working_rows
            )

    worker_statuses = Counter(str(run.get("status") or "") for run in worker_runs)
    counts = dict(queue_payload.get("counts") or {})
    counts.update(
        {
            "queue_items": len(queue_payload.get("items") or []),
            "selected_items": len(selected),
            "worker_runs": len(worker_runs),
            "accepted": sum(int((run.get("counts") or {}).get("accepted") or 0) for run in worker_runs),
            "parked": sum(int((run.get("counts") or {}).get("parked") or 0) for run in worker_runs),
            "rejected": sum(int((run.get("counts") or {}).get("rejected") or 0) for run in worker_runs),
            "worker_failure": sum(1 for run in worker_runs if run.get("status") in {"worker_error", "pack_missing"}),
            "written_queue_rows": written["queue"],
            "written_findings": written["findings"],
            "written_working_memory": written["working_memory"],
        }
    )
    return {
        "schema_version": 1,
        "kind": SLEEP_CYCLE_KIND,
        "created_at": format_utc(normalize_now(now)),
        "execution_mode": dream_queue.EXECUTION_MODE,
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "no_write": bool(no_write),
        "write_mode": "no_write"
        if no_write
        else "full"
        if write_working_memory
        else "staging",
        "run_ready": bool(run_ready),
        "queue": queue_payload,
        "selected_queue_items": selected,
        "worker_runs": worker_runs,
        "queue_lifecycle_rows": lifecycle_rows,
        "adjudicated_findings": adjudicated_findings,
        "dream_working_memory_rows": working_rows,
        "counts": counts,
        "worker_statuses": dict(sorted(worker_statuses.items())),
        "failure_buckets": failure_buckets(worker_runs),
        "cache": aggregate_cache(worker_runs),
        "policy": {
            "foreground_model_calls_allowed": False,
            "clean_source_mutation_allowed": False,
            "default_no_write": True,
            "writes_require_explicit_write_mode": True,
            "working_memory_projection_requires_full_write": True,
            "queue_state_is_not_clean_source": True,
        },
    }


def public_sleep_cycle_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") or {}
    return {
        "kind": SUMMARY_KIND,
        "execution_mode": payload.get("execution_mode"),
        "foreground_model_calls_allowed": False,
        "no_write": bool(payload.get("no_write")),
        "write_mode": payload.get("write_mode") or "no_write",
        "run_ready": bool(payload.get("run_ready")),
        "counts": {
            "queue_items": int(counts.get("queue_items") or 0),
            "selected_items": int(counts.get("selected_items") or 0),
            "accepted": int(counts.get("accepted") or 0),
            "parked": int(counts.get("parked") or 0),
            "rejected": int(counts.get("rejected") or 0),
            "worker_failure": int(counts.get("worker_failure") or 0),
            "skipped_duplicate": int(counts.get("skipped_duplicate") or 0),
            "expired": int(counts.get("expired") or 0),
            "written_findings": int(counts.get("written_findings") or 0),
            "written_working_memory": int(counts.get("written_working_memory") or 0),
        },
        "worker_statuses": dict(payload.get("worker_statuses") or {}),
        "failure_buckets": dict(payload.get("failure_buckets") or {}),
        "cache": dict(payload.get("cache") or {}),
        "policy": {
            "public_output_omits_private_handles": True,
            "queue_state_is_not_clean_source": True,
            "clean_source_mutation_allowed": False,
        },
    }


def row_mentions_project(row: Mapping[str, Any], project: str | None) -> bool:
    if not project:
        return True
    wanted = project.casefold()
    labels = [row.get("project_label")]
    for ref in row.get("source_refs") or []:
        if isinstance(ref, Mapping):
            labels.append(ref.get("project_label"))
    return any(wanted == str(label or "").casefold() for label in labels)


def load_registry_seed_rows(root: Path, *, project: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in REGISTRY_SEED_FILES:
        for row in iter_jsonl(root / name):
            if row_mentions_project(row, project):
                rows.append(row)
    return rows


def packs_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.packs_jsonl:
        return iter_jsonl(Path(args.packs_jsonl))
    if not args.registry_dir:
        raise ValueError("--packs-jsonl or --registry-dir is required")
    root = Path(args.registry_dir)
    seed_rows = load_registry_seed_rows(root, project=args.project)
    if not seed_rows:
        return []
    objective = args.objective or f"Run bounded dream sleep-cycle for project {args.project or 'default'}."
    return [dream_input_pack.build_dream_input_pack(seed_rows, objective=objective)]


def config_from_args(args: argparse.Namespace) -> ChatClientConfig:
    route = resolve_model_route(
        args.model_route,
        explicit_model=args.model if args.model != flash_model() and not args.model_route else None,
        explicit_base_url=args.base_url if args.base_url != deepseek_base_url() and not args.model_route else None,
        explicit_api_key_env=args.api_key_env if args.api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV else None,
    )
    model = route.model if args.model == flash_model() else args.model
    base_url = route.base_url if args.base_url == deepseek_base_url() else args.base_url
    api_key_env = args.api_key_env or route.api_key_env
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"missing API key env: {api_key_env}")
    cache_contract = (
        DEEPSEEK_PREFIX_CACHE_CONTRACT
        if route.provider == "deepseek"
        else NO_PROVIDER_CACHE_CONTRACT
    )
    return ChatClientConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        service_name=route_service_name(route),
        cache_contract=cache_contract,
    )


def default_path(root: Path | None, name: str, override: Path | None) -> Path | None:
    if override:
        return override
    if root:
        return root / name
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run detached background dream queue items.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--packs-jsonl", type=Path)
    parser.add_argument("--previous-queue-jsonl", type=Path)
    parser.add_argument("--findings-jsonl", type=Path)
    parser.add_argument("--queue-output", type=Path)
    parser.add_argument("--findings-output", type=Path)
    parser.add_argument("--working-memory-output", type=Path)
    parser.add_argument("--objective", default="")
    parser.add_argument("--now")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--max-samples", type=int, default=DEFAULT_MAX_SAMPLES)
    parser.add_argument("--run-ready", action="store_true")
    parser.add_argument("--no-write", action="store_true", help="Keep projected results in stdout only.")
    parser.add_argument(
        "--write-staging",
        action="store_true",
        help="Append queue lifecycle and adjudicated findings, but do not project working-memory rows.",
    )
    parser.add_argument("--write", action="store_true", help="Append lifecycle/findings/working-memory staging rows.")
    parser.add_argument("--summary", action="store_true", help="Emit sanitized aggregate summary only.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=flash_model())
    parser.add_argument("--base-url", default=deepseek_base_url())
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-tokens", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        root = Path(args.registry_dir).resolve() if args.registry_dir else None
        packs = packs_from_args(args)
        previous = iter_jsonl(args.previous_queue_jsonl or default_path(root, "dream_queue.jsonl", None))
        existing = iter_jsonl(args.findings_jsonl or default_path(root, "dream_findings.jsonl", None))
        if args.write and args.write_staging:
            raise ValueError("--write and --write-staging are mutually exclusive")
        no_write = not bool(args.write or args.write_staging)
        payload = run_sleep_cycle(
            packs,
            previous_items=previous,
            existing_findings=existing,
            now=args.now or now_utc(),
            config=config_from_args(args) if packs else None,
            max_items=args.max_items,
            max_samples=args.max_samples,
            no_write=no_write,
            write_working_memory=bool(args.write),
            run_ready=args.run_ready,
            queue_output_path=default_path(root, "dream_queue.jsonl", args.queue_output),
            findings_output_path=default_path(root, "dream_findings.jsonl", args.findings_output),
            working_memory_output_path=default_path(root, "working_memory.jsonl", args.working_memory_output),
        )
        output_payload = public_sleep_cycle_summary(payload) if args.summary else payload
        text = json.dumps(output_payload, ensure_ascii=False, indent=None if args.json_output else 2)
        write_json(args.output, output_payload)
        print(text)
        return 0
    except Exception as exc:
        payload = cli_error_payload(exc)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"], flush=True)
        return cli_exit_code_for_error_code(str(payload.get("code") or ""))


if __name__ == "__main__":
    raise SystemExit(main())
