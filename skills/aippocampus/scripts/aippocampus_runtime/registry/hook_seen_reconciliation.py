"""Hook-seen ledger reconciliation into registry clean source."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home, codex_provider, public_session_meta
from aippocampus_runtime.registry.source_registration import register_rollout_thread
from aippocampus_runtime.registry.store import load_registry, registry_paths
from aippocampus_runtime.warm_ambient.hook_seen_threads import (
    DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
    HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED,
    HOOK_SEEN_STATE_PENDING_REPAIR,
    HOOK_SEEN_STATE_REGISTERED,
    HOOK_SEEN_STATE_STALE_LEDGER_ROW,
    hook_seen_ledger_path_for_registry,
    hook_seen_thread_ref,
    latest_hook_seen_by_ref,
    project_hook_seen_state,
)
from conversation_sources import ConversationProvider


def _discover_sources_by_hook_seen_ref(
    provider: ConversationProvider,
) -> dict[str, tuple[float, Path, dict[str, Any], str]]:
    discovered: dict[str, tuple[float, Path, dict[str, Any], str]] = {}
    for source in provider.discover_sessions():
        rollout = source.path
        meta = dict(source.metadata or {})
        if not meta:
            meta = public_session_meta(provider.read_metadata(source))
        thread_key = provider.thread_key(source, meta)
        thread_ref = hook_seen_thread_ref(thread_key)
        if not thread_ref:
            continue
        try:
            mtime = rollout.stat().st_mtime
        except OSError:
            continue
        previous = discovered.get(thread_ref)
        if previous is None or mtime > previous[0]:
            discovered[thread_ref] = (mtime, rollout, meta, thread_key)
    return discovered


def _count_hook_seen_states(states: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        HOOK_SEEN_STATE_REGISTERED: 0,
        HOOK_SEEN_STATE_PENDING_REPAIR: 0,
        HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED: 0,
        HOOK_SEEN_STATE_STALE_LEDGER_ROW: 0,
    }
    for item in states:
        state = str(item.get("state") or "")
        if state in counts:
            counts[state] += 1
    return counts


def reconcile_hook_seen_threads(
    *,
    registry_dir: Path | None = None,
    build_index: bool = False,
    max_count: int | None = None,
    dry_run: bool = False,
    hook_seen_ledger: Path | None = None,
    stale_after_seconds: int = DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
    include_private_keys: bool = False,
    provider: ConversationProvider | None = None,
) -> dict[str, Any]:
    """Register hook-seen provider sessions as durable clean-source entries.

    The hook-seen ledger is only a reconciliation queue, so this function never
    treats hook output or warm cache material as evidence. It reopens provider
    discovery and then calls the normal registry/clean-source registration path.
    Heavy indexes remain opt-in through ``build_index``.
    """
    json_path, _ = registry_paths(registry_dir)
    registry_data = load_registry(json_path)
    existing_thread_keys = {
        str(entry.get("thread_key") or "")
        for entry in registry_data.get("threads", [])
        if str(entry.get("thread_key") or "").strip()
    }
    registered_refs = {hook_seen_thread_ref(key) for key in existing_thread_keys}
    ledger_path = hook_seen_ledger or hook_seen_ledger_path_for_registry(json_path)
    latest_rows = latest_hook_seen_by_ref(ledger_path)
    active_provider = provider or codex_provider(codex_home())
    discovered = _discover_sources_by_hook_seen_ref(active_provider)
    discoverable_refs = set(discovered)

    states: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    registered: list[dict[str, Any]] = []
    eligible_seen = 0

    for thread_ref, row in sorted(latest_rows.items()):
        state = project_hook_seen_state(
            row,
            registered_refs=registered_refs,
            discoverable_refs=discoverable_refs,
            stale_after_seconds=stale_after_seconds,
            include_private_keys=include_private_keys,
        )
        if state.get("state") == HOOK_SEEN_STATE_PENDING_REPAIR and thread_ref in discovered:
            if max_count is not None and eligible_seen >= max_count:
                state["diagnostic"] = "repair_budget_exhausted"
                state["next_action"] = "rerun_with_larger_max"
                states.append(state)
                continue
            eligible_seen += 1
            _mtime, rollout, meta, thread_key = discovered[thread_ref]
            action: dict[str, Any] = {
                "thread_ref": thread_ref,
                "source_provider": active_provider.name,
                "will_build_index": build_index,
            }
            if include_private_keys:
                action.update(
                    {
                        "thread_key": thread_key,
                        "rollout": str(rollout),
                        "cwd": meta.get("cwd"),
                        "timestamp": meta.get("timestamp"),
                    }
                )
            if dry_run:
                planned.append(action)
                state["action"] = "would_register_clean_source"
                state["next_action"] = "rerun_without_dry_run"
                states.append(state)
                continue

            result = register_rollout_thread(
                rollout,
                registry_dir=registry_dir,
                build_index=build_index,
                provider=active_provider,
            )
            entry = result["entry"]
            registered_refs.add(hook_seen_thread_ref(str(entry.get("thread_key") or "")))
            registered_item: dict[str, Any] = {
                "thread_ref": thread_ref,
                "source_provider": entry.get("source_provider"),
                "clean_source": True,
                "index_built": bool(build_index),
            }
            if include_private_keys:
                registered_item.update(
                    {
                        "thread_key": entry.get("thread_key"),
                        "clean_source_dir": entry.get("paths", {}).get("clean_source_dir"),
                        "index_dir": entry.get("paths", {}).get("index_dir"),
                    }
                )
            registered.append(registered_item)
            state.update(
                {
                    "state": HOOK_SEEN_STATE_REGISTERED,
                    "status": HOOK_SEEN_STATE_REGISTERED,
                    "diagnostic": "registered_clean_source",
                    "action": "registered_clean_source",
                    "next_action": "none",
                }
            )
        states.append(state)

    state_counts = _count_hook_seen_states(states)
    not_registered_count = (
        state_counts[HOOK_SEEN_STATE_PENDING_REPAIR]
        + state_counts[HOOK_SEEN_STATE_STALE_LEDGER_ROW]
    )
    blocked_count = state_counts[HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED]
    candidates = [
        item
        for item in states
        if item.get("state")
        in {
            HOOK_SEEN_STATE_PENDING_REPAIR,
            HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED,
            HOOK_SEEN_STATE_STALE_LEDGER_ROW,
        }
    ][:20]
    return {
        "kind": "aippocampus_hook_seen_auto_reconciliation",
        "schema_version": 1,
        "status": "degraded" if (not_registered_count or blocked_count) else "ok",
        "registry": str(json_path),
        "ledger": str(ledger_path),
        "dry_run": dry_run,
        "artifact_policy": {
            "clean_source_registration": True,
            "heavy_index_rebuild_default": False,
            "heavy_index_rebuild_requested": build_index,
            "hook_output_is_evidence": False,
        },
        "metrics": {
            "hook_seen_thread_count": len(latest_rows),
            "discoverable_hook_seen_thread_count": len(
                set(latest_rows).intersection(discoverable_refs)
            ),
            "registered_hook_seen_thread_count": state_counts[HOOK_SEEN_STATE_REGISTERED],
            "pending_repair_count": state_counts[HOOK_SEEN_STATE_PENDING_REPAIR],
            "blocked_or_unsupported_count": blocked_count,
            "stale_ledger_row_count": state_counts[HOOK_SEEN_STATE_STALE_LEDGER_ROW],
            "hook_seen_but_not_registered_count": not_registered_count,
            "planned_clean_source_registration_count": len(planned),
            "automatic_clean_source_registration_count": len(registered),
            "manual_thread_id_investigation_reduced_count": len(planned) + len(registered),
            "state_counts": state_counts,
        },
        "planned": planned,
        "registered": registered,
        "candidates": candidates,
        "states": states[:20],
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_thread_ids_emitted": include_private_keys,
            "local_paths_emitted": include_private_keys,
            "ledger_is_private_operator_state": True,
        },
    }
