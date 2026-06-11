"""Private hook-seen thread ledger for registry reconciliation.

Prompt hooks can observe a fresh Codex thread before lifecycle registration has
materialized clean-source artifacts. This ledger is intentionally tiny: it
records only thread identity and hashed workspace metadata so a later health or
repair command can detect "hook saw it, registry missed it" without treating
the warm cache as source evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc, stable_text_fingerprint, workspace_fingerprint

HOOK_SEEN_SCHEMA_VERSION = 1
DEFAULT_HOOK_SEEN_LEDGER_NAME = "hook_seen_threads.jsonl"


def hook_seen_ledger_path_for_cache(cache_path: Path | str) -> Path:
    return Path(cache_path).resolve().with_name(DEFAULT_HOOK_SEEN_LEDGER_NAME)


def hook_seen_ledger_path_for_registry(registry_path: Path | str) -> Path:
    return Path(registry_path).resolve().parent / DEFAULT_HOOK_SEEN_LEDGER_NAME


def thread_key_from_hook_thread_id(thread_id: str | None) -> str | None:
    text = str(thread_id or "").strip()
    if not text:
        return None
    if ":" in text:
        return text
    return f"session:{text}"


def record_hook_seen_thread(
    ledger_path: Path | str,
    *,
    thread_id: str | None,
    workspace: str,
    current_thread_key: str | None = None,
    topic_epoch: str | None = None,
    event: str = "UserPromptSubmit",
) -> dict[str, Any]:
    thread_key = current_thread_key or thread_key_from_hook_thread_id(thread_id)
    if not thread_key:
        return {"status": "skipped", "reason": "missing_thread_id"}
    path = Path(ledger_path).resolve()
    row = {
        "kind": "aippocampus_hook_seen_thread",
        "schema_version": HOOK_SEEN_SCHEMA_VERSION,
        "recorded_at": now_utc(),
        "event": event,
        # Raw thread ids stay only in the private operator ledger. Public health
        # diagnostics use the fingerprint below.
        "thread_id": str(thread_id or thread_key),
        "thread_key": thread_key,
        "thread_ref": stable_text_fingerprint(thread_key, namespace="hook-seen-thread", prefix="hst"),
        "workspace_ref": workspace_fingerprint(workspace, prefix="workspace"),
        "topic_epoch": topic_epoch or "",
        "registration_expectation": "registry_clean_source_or_blocked",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "status": "recorded",
        "thread_ref": row["thread_ref"],
        "ledger_private": True,
    }


def load_hook_seen_rows(path: Path | str, *, max_rows: int = 512) -> list[dict[str, Any]]:
    ledger = Path(path)
    if not ledger.exists():
        return []
    rows: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("thread_key"):
                rows.append(parsed)
    if max_rows > 0 and len(rows) > max_rows:
        rows = rows[-max_rows:]
    return rows


def latest_hook_seen_by_thread(path: Path | str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in load_hook_seen_rows(path):
        thread_key = str(row.get("thread_key") or "")
        if thread_key:
            latest[thread_key] = row
    return latest


def hook_seen_thread_keys(path: Path | str) -> set[str]:
    return set(latest_hook_seen_by_thread(path))


def hook_seen_registry_diagnostic(
    ledger_path: Path | str,
    *,
    registered_thread_keys: Iterable[str],
    include_private_keys: bool = False,
) -> dict[str, Any]:
    latest = latest_hook_seen_by_thread(ledger_path)
    registered = {str(key) for key in registered_thread_keys if str(key or "").strip()}
    missing = [
        row for thread_key, row in sorted(latest.items()) if thread_key not in registered
    ]
    candidates: list[dict[str, Any]] = []
    for row in missing[:20]:
        candidate = {
            "thread_ref": row.get("thread_ref")
            or stable_text_fingerprint(str(row.get("thread_key") or ""), namespace="hook-seen-thread", prefix="hst"),
            "status": "hook_seen_but_not_registered",
            "next_action": "run_registry_scan_hook_seen_only",
        }
        if include_private_keys:
            candidate["thread_key"] = row.get("thread_key")
        candidates.append(candidate)
    return {
        "kind": "aippocampus_hook_seen_registry_reconciliation",
        "schema_version": HOOK_SEEN_SCHEMA_VERSION,
        "status": "degraded" if missing else "ok",
        "metrics": {
            "hook_seen_thread_count": len(latest),
            "registered_hook_seen_thread_count": len(set(latest).intersection(registered)),
            "hook_seen_but_not_registered_count": len(missing),
        },
        "candidates": candidates,
        "repair_command": (
            "python -m aippocampus_runtime.registry.api scan-sessions "
            "--hook-seen-only --dry-run --json"
        ),
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_thread_ids_emitted": include_private_keys,
            "local_paths_emitted": False,
            "ledger_is_private_operator_state": True,
        },
    }
