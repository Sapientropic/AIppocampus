#!/usr/bin/env python3
"""Sanitized real-history smoke for fresh-thread recall #302 boundaries.

This smoke runs against a real registry when available, but its output is
aggregate/hash-only. It must not print prompts, snippets, thread ids, source
refs, registry paths, or local workspace paths. The goal is to verify the two
real-history integration boundaries from #302 without turning private history
into a public artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_prompt_hook import assess_prompt  # noqa: E402
from aippocampus_runtime.recall import active_recall_lock as locks  # noqa: E402
from aippocampuslib import aippocampus_registry_dir  # noqa: E402
from registry import load_registry  # noqa: E402

SMOKE_KIND = "aippocampus_fresh_thread_real_history_smoke"
PRIVACY_BOUNDARY = "aggregate_hash_only_no_prompts_no_source_text_no_paths_no_refs"
CURRENT_REPO_FACT_PROMPT = "请给这个 repo 的 source-backed evidence：测试命令是什么？"


def stable_hash(value: str, *, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def iter_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    if not path.is_file():
        return rows, bad_rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                bad_rows += 1
                continue
            if isinstance(item, dict):
                rows.append(item)
            else:
                bad_rows += 1
    return rows, bad_rows


def clean_source_messages_path(entry: dict[str, Any]) -> Path | None:
    paths = dict_value(entry.get("paths"))
    raw = paths.get("clean_source_messages_jsonl")
    return Path(str(raw)) if raw else None


def candidate_ref_from_message(thread_key: str, row: dict[str, Any]) -> dict[str, Any] | None:
    ref: dict[str, Any] = {"thread_key": thread_key}
    for key in ("message_id", "turn_id", "turn_index", "phase"):
        value = row.get(key)
        if value not in {None, ""}:
            ref[key] = value
    line = row.get("source_line", row.get("line"))
    if line not in {None, ""}:
        ref["line"] = line
    if locks.reopenable_ref_count([ref]) <= 0:
        return None
    return ref


def select_reopenable_refs(registry: dict[str, Any], *, limit: int = 3) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    bad_rows = 0
    clean_source_paths = 0
    clean_source_paths_found = 0
    message_rows_seen = 0

    for entry in list_value(registry.get("threads")):
        if not isinstance(entry, dict):
            continue
        thread_key = str(entry.get("thread_key") or "")
        if not thread_key:
            continue
        messages_path = clean_source_messages_path(entry)
        if messages_path is None:
            continue
        clean_source_paths += 1
        if not messages_path.is_file():
            continue
        clean_source_paths_found += 1
        rows, row_errors = iter_jsonl(messages_path)
        bad_rows += row_errors
        message_rows_seen += len(rows)
        for row in rows:
            ref = candidate_ref_from_message(thread_key, row)
            if ref:
                selected.append(ref)
                break
        if len(selected) >= limit:
            break

    return {
        "selected_refs": selected,
        "stats": {
            "thread_count": len(list_value(registry.get("threads"))),
            "clean_source_message_path_count": clean_source_paths,
            "clean_source_message_path_found_count": clean_source_paths_found,
            "clean_source_message_rows_seen": message_rows_seen,
            "bad_clean_source_message_rows": bad_rows,
            "selected_reopenable_thread_count": len(selected),
        },
    }


def run_ready_lock_reopenability_check(
    *,
    registry_path: Path,
    cwd: Path,
    ref: dict[str, Any] | None,
) -> dict[str, Any]:
    if ref is None:
        return {"status": "insufficient_real_history", "reason": "no_reopenable_ref"}
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "active_recall_locks.json"
        lock = locks.start_or_update_recall_lock(
            lock_path,
            prompt="fresh-thread real-history reopenability boundary",
            thread_id="fresh_thread_real_history",
            workspace=cwd,
            topic_epoch="fresh_thread_real_history",
            registry_path=registry_path,
            candidate_refs=[ref],
            state="ready",
            route_reasons=["real_history_reopenability_smoke"],
        )
        reopened = locks.reopen_lock_sources(
            lock_path,
            lock_id=lock["lock_id"],
            registry_path=registry_path,
        )

    match_count = len(list_value(reopened.get("matches")))
    passed = lock.get("state") == "ready" and bool(reopened.get("ok")) and match_count > 0
    return {
        "status": "passed" if passed else "failed",
        "lock_state": str(lock.get("state") or ""),
        "reopen_ok": bool(reopened.get("ok")),
        "match_count": match_count,
        "reopenable_ref_count": int_count(lock.get("reopenable_ref_count")),
    }


def run_thread_only_lock_boundary_check(
    *,
    registry_path: Path,
    cwd: Path,
    ref: dict[str, Any] | None,
) -> dict[str, Any]:
    if ref is None:
        return {"status": "insufficient_real_history", "reason": "no_thread_ref"}
    thread_key = str(ref.get("thread_key") or "")
    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "active_recall_locks.json"
        lock = locks.start_or_update_recall_lock(
            lock_path,
            prompt="fresh-thread real-history thread-only boundary",
            thread_id="fresh_thread_real_history",
            workspace=cwd,
            topic_epoch="fresh_thread_real_history",
            registry_path=registry_path,
            candidate_refs=[{"thread_key": thread_key}],
            state="ready",
            route_reasons=["real_history_thread_only_smoke"],
        )
        reopened = locks.reopen_lock_sources(
            lock_path,
            lock_id=lock["lock_id"],
            registry_path=registry_path,
        )

    passed = (
        lock.get("state") == "pending"
        and int_count(lock.get("reopenable_ref_count")) == 0
        and not bool(reopened.get("ok"))
        and str(reopened.get("state") or "") == "pending"
    )
    return {
        "status": "passed" if passed else "failed",
        "lock_state": str(lock.get("state") or ""),
        "reopen_ok": bool(reopened.get("ok")),
        "reopenable_ref_count": int_count(lock.get("reopenable_ref_count")),
        "error_codes": [
            stable_hash(str(item.get("code") or "unknown"), length=10)
            for item in list_value(reopened.get("errors"))
            if isinstance(item, dict)
        ],
    }


def run_current_repo_fact_negative_control(
    *,
    registry_path: Path,
    cwd: Path,
) -> dict[str, Any]:
    result = assess_prompt(
        CURRENT_REPO_FACT_PROMPT,
        cwd=cwd,
        registry_path=registry_path,
        semantic_gate_mode="off",
        use_semantic_gate=False,
        search_budget=2,
        warm_background=False,
    )
    reasons = " ".join(str(reason or "") for reason in result.get("reasons") or [])
    evidence_count = len(list_value(result.get("evidence")))
    candidate_count = len(list_value(result.get("candidates")))
    current_checkout_required = "current checkout required" in reasons.casefold()
    passed = evidence_count == 0 and str(result.get("decision") or "") != "evidence"
    return {
        "status": "passed" if passed else "failed",
        "decision": str(result.get("decision") or ""),
        "evidence_count": evidence_count,
        "candidate_count": candidate_count,
        "current_checkout_required": current_checkout_required,
        "context_would_be_empty": evidence_count == 0,
    }


def run_fresh_thread_real_history_smoke(
    *,
    registry_path: Path,
    cwd: Path,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    selected = select_reopenable_refs(registry, limit=1)
    refs = list_value(selected.get("selected_refs"))
    ref = refs[0] if refs and isinstance(refs[0], dict) else None

    checks = {
        "ready_lock_reopenability": run_ready_lock_reopenability_check(
            registry_path=registry_path,
            cwd=cwd,
            ref=ref,
        ),
        "thread_only_lock_boundary": run_thread_only_lock_boundary_check(
            registry_path=registry_path,
            cwd=cwd,
            ref=ref,
        ),
        "current_repo_fact_negative_control": run_current_repo_fact_negative_control(
            registry_path=registry_path,
            cwd=cwd,
        ),
    }
    statuses = [str(check.get("status") or "") for check in checks.values()]
    insufficient = any(status == "insufficient_real_history" for status in statuses)
    failed = any(status == "failed" for status in statuses)
    status = "insufficient_real_history" if insufficient else "failed" if failed else "passed"
    ok = status == "passed"
    return {
        "kind": SMOKE_KIND,
        "privacy": "aggregate_hash_only",
        "privacy_boundary": PRIVACY_BOUNDARY,
        "ok": ok,
        "status": status,
        "registry": selected["stats"],
        "registry_fingerprint": stable_hash(json.dumps(selected["stats"], sort_keys=True)),
        "checks": checks,
        "can_claim": (
            ["real-history fresh-thread recall boundary passed"]
            if ok
            else []
        ),
        "cannot_claim": (
            []
            if ok
            else ["real-history fresh-thread recall boundary passed"]
        )
        + [
            "private real-history recall quality",
            "live semantic-model quality",
            "broad production coverage for all fresh-thread prompts",
        ],
    }


def print_table(result: dict[str, Any]) -> None:
    print(
        "fresh-thread real-history smoke: "
        f"{result.get('status')} | "
        f"threads={dict_value(result.get('registry')).get('thread_count', 0)} | "
        f"selected={dict_value(result.get('registry')).get('selected_reopenable_thread_count', 0)}"
    )
    for name, check in dict_value(result.get("checks")).items():
        print(f"- {name}: {dict_value(check).get('status')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    result = run_fresh_thread_real_history_smoke(
        registry_path=registry_path,
        cwd=Path(args.cwd).resolve(),
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(result)
    return 1 if args.strict and not result["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
