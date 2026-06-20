#!/usr/bin/env python3
"""Short-lived active-recall locks for agent-owned source reopen.

Recall locks are route handles, not memories and not evidence. They deliberately
store only hashed prompt/workspace identities, compact aliases, candidate source
refs, and diagnostics. Exact claims must reopen clean source by lock id.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.artifacts.publish import artifact_lease
from aippocampus_runtime.core import (
    compact_text,
    now_utc,
    sanitize_external_model_text,
    stable_text_fingerprint,
    workspace_fingerprint,
    workspace_identity,
)
from aippocampus_runtime.recall.active_recall_lock_lifecycle import (
    bump_roi_metrics,
    freshness_vector,
    summarize_lock_roi_entries,
)
from aippocampus_runtime.recall.active_recall_lock_lifecycle import (
    nonnegative_int as _nonnegative_int,
)
from aippocampus_runtime.recall.active_recall_lock_lifecycle import (
    roi_metrics as _roi_metrics,
)
from aippocampus_runtime.recall.active_recall_lock_public import (
    LOCK_SCHEMA_VERSION,
    LOCK_STATES,
    reopenable_ref_count,
)
from aippocampus_runtime.recall.active_recall_lock_public import (
    public_lock as _public_lock,
)
from aippocampus_runtime.recall.ambient_cache import default_ambient_cache_path
from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.search import iter_clean_messages

DEFAULT_LOCK_NAME = "active_recall_locks.json"
DEFAULT_TTL_SECONDS = 20 * 60
DEFAULT_MAX_ENTRIES = 128
DEFAULT_MAX_REFS = 12
DEFAULT_MAX_ALIASES = 16
DEFAULT_MAX_ROUTE_REASONS = 12


def _sha(value: str, *, prefix: str) -> str:
    return stable_text_fingerprint(
        value,
        namespace=f"active-recall-lock-{prefix}",
        prefix=prefix,
        length=20,
    )


def _prompt_fingerprint(prompt: str, query_aliases: list[str] | None = None) -> str:
    parts = [_safe_text(prompt, 480).casefold()]
    parts.extend(_safe_text(alias, 160).casefold() for alias in query_aliases or [])
    return _sha("\n".join(parts), prefix="prompt")


def _thread_fingerprint(thread_id: str | None) -> str:
    return _sha(str(thread_id or ""), prefix="thread")


def registry_freshness_fingerprint(registry_path: Path | str | None) -> str:
    if registry_path is None:
        return "registry_unknown"
    path = Path(registry_path)
    try:
        stat = path.stat()
    except OSError:
        return "registry_missing"
    return _sha(f"{stat.st_mtime_ns}:{stat.st_size}", prefix="registry")


def default_active_recall_lock_path(
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
) -> Path:
    cache_path = default_ambient_cache_path(
        registry_path=Path(registry_path).resolve() if registry_path else None,
        registry_dir=Path(registry_dir).resolve() if registry_dir else None,
    )
    return cache_path.resolve().parent / DEFAULT_LOCK_NAME


def lock_id_for_route(
    *,
    prompt: str,
    thread_id: str | None,
    workspace: str | Path,
    topic_epoch: str | None,
    registry_freshness: str,
    query_aliases: list[str] | None = None,
) -> str:
    workspace_key = workspace_identity(workspace)
    seed = "\n".join(
        [
            _prompt_fingerprint(prompt),
            _thread_fingerprint(thread_id),
            workspace_fingerprint(workspace_key),
            str(topic_epoch or "epoch_unknown"),
            registry_freshness,
        ]
    )
    return _sha(seed, prefix="arl")


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": LOCK_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": LOCK_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    if not isinstance(data, dict):
        return {"schema_version": LOCK_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    if not isinstance(data.get("entries"), dict):
        data["entries"] = {}
    data["schema_version"] = LOCK_SCHEMA_VERSION
    return data


def _write_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _with_store_writer(
    path: Path,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    deadline = time.time() + max(0.1, timeout_seconds)
    while True:
        try:
            with artifact_lease(
                path.parent,
                path.name + ".lock",
                stale_after_seconds=30,
            ):
                data = _load_store(path)
                result = mutate(data)
                raw_entries = data.get("entries")
                entries: dict[str, Any] = raw_entries if isinstance(raw_entries, dict) else {}
                kept = sorted(
                    entries.items(),
                    key=lambda item: float((item[1] or {}).get("updated_unix") or 0.0),
                    reverse=True,
                )[:DEFAULT_MAX_ENTRIES]
                data["entries"] = dict(kept)
                data["updated_at"] = now_utc()
                data["schema_version"] = LOCK_SCHEMA_VERSION
                _write_store(path, data)
                return result
        except RuntimeError:
            if time.time() >= deadline:
                raise
            time.sleep(0.01)


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _looks_sensitive_alias(text: str) -> bool:
    low = text.casefold()
    if re.search(r"(api[_-]?key|secret|token|password|credential)\s*[:=]", low):
        return True
    if any(marker in low for marker in ("secret", "password", "credential")):
        return True
    if (
        re.fullmatch(r"[A-Za-z0-9]{6,}", text)
        and any(char.isalpha() for char in text)
        and any(char.isdigit() for char in text)
    ):
        return True
    return bool("token" in low and ("=" in low or "_" in text))


def _unique_text(values: list[Any] | None, *, limit: int, chars: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _safe_text(value, chars)
        if not text:
            continue
        if _looks_sensitive_alias(text):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _clean_candidate_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    clean: dict[str, Any] = {}
    key_map = {
        "stable_source_id": "source_id",
        "source_id": "source_id",
        "thread_key": "thread_key",
        "message_id": "message_id",
        "turn_id": "turn_id",
        "turn_index": "turn_index",
        "source_line": "line",
        "line": "line",
        "phase": "phase",
        "segment_id": "segment_id",
        "segment_line": "segment_line",
    }
    for key, out_key in key_map.items():
        value = ref.get(key)
        if value in {None, ""}:
            continue
        clean[out_key] = compact_text(str(value), 120)
    return clean or None


def _clean_candidate_refs(values: list[Any] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for value in values or []:
        clean = _clean_candidate_ref(value)
        if not clean:
            continue
        key = tuple(sorted((str(k), str(v)) for k, v in clean.items()))
        if key in seen:
            continue
        seen.add(key)
        refs.append(clean)
        if len(refs) >= DEFAULT_MAX_REFS:
            break
    return refs


def _merge_refs(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _clean_candidate_refs([*left, *right])


def _future_pair(ttl_seconds: int) -> tuple[str, float]:
    expires = time.time() + max(1, ttl_seconds)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires)), expires


def _bump_lock_roi(path: Path, lock_id: str, **deltas: int) -> dict[str, int]:
    def mutate(data: dict[str, Any]) -> dict[str, int]:
        entry = (data.setdefault("entries", {}) or {}).get(lock_id)
        if not isinstance(entry, dict):
            return _roi_metrics()
        metrics = bump_roi_metrics(entry.get("roi_metrics"), **deltas)
        entry["roi_metrics"] = metrics
        data["entries"][lock_id] = entry
        return metrics

    return _with_store_writer(path, mutate)


def _candidate_refs_from_cards(cards: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        refs.extend([ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)])
    return _clean_candidate_refs(refs)


def start_or_update_recall_lock(
    path: Path | str,
    *,
    prompt: str,
    thread_id: str | None,
    workspace: str | Path,
    topic_epoch: str | None,
    registry_path: Path | str | None = None,
    candidate_refs: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    query_aliases: list[str] | None = None,
    route_reasons: list[str] | None = None,
    conflict_flags: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
    freshness_sources: list[dict[str, Any]] | None = None,
    state: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    target = Path(path)
    refs = _merge_refs(_clean_candidate_refs(candidate_refs), _candidate_refs_from_cards(cards))
    aliases = _unique_text(query_aliases, limit=DEFAULT_MAX_ALIASES, chars=120)
    registry_fp = registry_freshness_fingerprint(Path(registry_path) if registry_path else None)
    lock_id = lock_id_for_route(
        prompt=prompt,
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        registry_freshness=registry_fp,
        query_aliases=aliases,
    )
    vector = freshness_vector(
        registry_freshness_fingerprint_value=registry_fp,
        freshness_sources=freshness_sources,
    )
    requested_state = (
        state if state in LOCK_STATES else ("ready" if reopenable_ref_count(refs) else "pending")
    )
    now = now_utc()
    now_unix = time.time()
    expires_at, expires_unix = _future_pair(ttl_seconds)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entries = data.setdefault("entries", {})
        old = entries.get(lock_id) if isinstance(entries.get(lock_id), dict) else {}
        created_at = old.get("created_at") or now
        created_unix = float(old.get("created_unix") or now_unix)
        merged_refs = _merge_refs(old.get("candidate_refs") or [], refs)
        merged_aliases = _unique_text(
            [*(old.get("query_aliases") or []), *aliases],
            limit=DEFAULT_MAX_ALIASES,
            chars=120,
        )
        merged_route_reasons = _unique_text(
            [*(old.get("route_reasons") or []), *(route_reasons or [])],
            limit=DEFAULT_MAX_ROUTE_REASONS,
            chars=160,
        )
        merged_conflicts = _unique_text(
            [*(old.get("conflict_flags") or []), *(conflict_flags or [])],
            limit=8,
            chars=80,
        )
        old_diagnostics = dict(old.get("diagnostics") or {})
        new_diagnostics = {
            key: _safe_text(value, 160) if isinstance(value, str) else value
            for key, value in (diagnostics or {}).items()
        }
        has_reopenable_refs = reopenable_ref_count(merged_refs) > 0
        final_state = requested_state
        if final_state == "ready" and not has_reopenable_refs:
            final_state = "pending"
            new_diagnostics["ready_downgraded_no_reopenable_refs"] = True
        if old.get("state") == "ready" and final_state == "pending" and has_reopenable_refs:
            final_state = "ready"
        if has_reopenable_refs and final_state == "pending" and state != "pending":
            final_state = "ready"
        old_state = str(old.get("state") or "missing")
        old_version = int(old.get("lock_version") or 0)
        enrichment_generation = int(old.get("enrichment_generation") or 0)
        consumer_metrics = dict(old.get("consumer_metrics") or {})
        roi_metrics = dict(old.get("roi_metrics") or {})
        entry = {
            "lock_id": lock_id,
            "kind": "aippocampus_active_recall_lock",
            "schema_version": LOCK_SCHEMA_VERSION,
            "lock_version": old_version + 1,
            "enrichment_generation": enrichment_generation,
            "state_transition": f"{old_state}->{final_state}",
            "state": final_state,
            "support_level": "scent",
            "prompt_fingerprint": _prompt_fingerprint(prompt),
            "thread_fingerprint": _thread_fingerprint(thread_id),
            "workspace_fingerprint": workspace_fingerprint(workspace),
            "topic_epoch": topic_epoch,
            "registry_freshness_fingerprint": registry_fp,
            "freshness_vector": vector,
            "candidate_refs": merged_refs,
            "query_aliases": merged_aliases,
            "route_reasons": merged_route_reasons,
            "conflict_flags": merged_conflicts,
            "source_reopen_required": True,
            "consumer_metrics": consumer_metrics,
            "enrichment_timing": dict(old.get("enrichment_timing") or {}),
            "roi_metrics": _roi_metrics(roi_metrics),
            "created_at": created_at,
            "created_unix": created_unix,
            "updated_at": now,
            "updated_unix": now_unix,
            "expires_at": expires_at,
            "expires_unix": expires_unix,
            "diagnostics": {**old_diagnostics, **new_diagnostics},
        }
        entries[lock_id] = entry
        return _public_lock(entry, now=now_unix)

    return _with_store_writer(target, mutate)


def enrich_recall_lock(
    path: Path | str,
    *,
    lock_id: str,
    candidate_refs: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    query_aliases: list[str] | None = None,
    route_reasons: list[str] | None = None,
    conflict_flags: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
    state: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    target = Path(path)
    refs = _merge_refs(_clean_candidate_refs(candidate_refs), _candidate_refs_from_cards(cards))
    aliases = _unique_text(query_aliases, limit=DEFAULT_MAX_ALIASES, chars=120)
    now = now_utc()
    now_unix = time.time()
    expires_at, expires_unix = _future_pair(ttl_seconds)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entries = data.setdefault("entries", {})
        entry = entries.get(lock_id)
        if not isinstance(entry, dict):
            failed = {
                "lock_id": lock_id,
                "lock_version": 1,
                "enrichment_generation": 0,
                "state_transition": "missing->failed",
                "state": "failed",
                "support_level": "scent",
                "candidate_refs": [],
                "query_aliases": aliases,
                "route_reasons": ["lock_missing_for_enrichment"],
                "conflict_flags": [],
                "source_reopen_required": True,
                "consumer_metrics": {},
                "enrichment_timing": {},
                "roi_metrics": _roi_metrics(),
                "diagnostics": {"reason": "missing_lock"},
            }
            return _public_lock(failed, now=now_unix)
        entry = dict(entry)
        old_state = str(entry.get("state") or "pending")
        old_expires_unix = float(entry.get("expires_unix") or 0.0)
        old_consumer_metrics = dict(entry.get("consumer_metrics") or {})
        entry["candidate_refs"] = _merge_refs(entry.get("candidate_refs") or [], refs)
        has_reopenable_refs = reopenable_ref_count(entry.get("candidate_refs") or []) > 0
        if state in LOCK_STATES:
            entry["state"] = state
        else:
            entry["state"] = "ready" if has_reopenable_refs else "pending"
        if entry["state"] == "ready" and not has_reopenable_refs:
            entry["state"] = "pending"
        entry["lock_version"] = int(entry.get("lock_version") or 0) + 1
        entry["enrichment_generation"] = int(entry.get("enrichment_generation") or 0) + 1
        entry["state_transition"] = f"{old_state}->{entry['state']}"
        entry["query_aliases"] = _unique_text(
            [*(entry.get("query_aliases") or []), *aliases],
            limit=DEFAULT_MAX_ALIASES,
            chars=120,
        )
        entry["route_reasons"] = _unique_text(
            [*(entry.get("route_reasons") or []), *(route_reasons or [])],
            limit=DEFAULT_MAX_ROUTE_REASONS,
            chars=160,
        )
        entry["conflict_flags"] = _unique_text(
            [*(entry.get("conflict_flags") or []), *(conflict_flags or [])],
            limit=8,
            chars=80,
        )
        safe_diagnostics = {
            key: _safe_text(value, 160) if isinstance(value, str) else value
            for key, value in (diagnostics or {}).items()
        }
        entry["diagnostics"] = {**dict(entry.get("diagnostics") or {}), **safe_diagnostics}
        first_read_unix = float(old_consumer_metrics.get("first_read_unix") or 0.0)
        entry["enrichment_timing"] = {
            "completed_after_first_read": bool(first_read_unix and now_unix > first_read_unix),
            "completed_after_expiry": bool(old_expires_unix and now_unix > old_expires_unix),
        }
        entry["consumer_metrics"] = old_consumer_metrics
        entry["roi_metrics"] = _roi_metrics(entry.get("roi_metrics"))
        entry["updated_at"] = now
        entry["updated_unix"] = now_unix
        entry["expires_at"] = expires_at
        entry["expires_unix"] = expires_unix
        entry["support_level"] = "scent"
        entry["source_reopen_required"] = True
        entries[lock_id] = entry
        return _public_lock(entry, now=now_unix)

    return _with_store_writer(target, mutate)


def read_recall_lock(
    path: Path | str,
    lock_id: str,
    *,
    topic_epoch: str | None = None,
    registry_freshness_fingerprint: str | None = None,
    freshness_sources: list[dict[str, Any]] | None = None,
    record_consumer_read: bool = True,
) -> dict[str, Any]:
    target = Path(path)
    data = _load_store(target)
    entry = (data.get("entries") or {}).get(lock_id)
    if not isinstance(entry, dict):
        return {
            "kind": "aippocampus_active_recall_lock",
            "schema_version": LOCK_SCHEMA_VERSION,
            "lock_id": lock_id,
            "lock_version": 0,
            "enrichment_generation": 0,
            "state_transition": "missing->missing",
            "state": "missing",
            "support_level": "scent",
            "candidate_refs": [],
            "candidate_ref_count": 0,
            "reopenable_ref_count": 0,
            "query_aliases": [],
            "route_reasons": [],
            "conflict_flags": [],
            "source_reopen_required": True,
            "suggested_next": "active_recall --mode probe --use-lock",
            "freshness_vector": {},
            "consumer_metrics": {"read_count": 0},
            "enrichment_timing": {},
            "roi_metrics": _roi_metrics(),
            "diagnostics": {"lock_age_ms": 0},
        }

    def project(entry_value: dict[str, Any]) -> dict[str, Any]:
        public = _public_lock(entry_value)
        invalidated_by = list((public.get("diagnostics") or {}).get("invalidated_by") or [])
        if topic_epoch is not None and entry_value.get("topic_epoch") != topic_epoch:
            invalidated_by.append("topic_epoch_changed")
        if (
            registry_freshness_fingerprint is not None
            and entry_value.get("registry_freshness_fingerprint") != registry_freshness_fingerprint
        ):
            invalidated_by.append("registry_freshness_changed")
        if freshness_sources is not None:
            current_vector = freshness_vector(
                registry_freshness_fingerprint_value=(
                    registry_freshness_fingerprint
                    or str(entry_value.get("registry_freshness_fingerprint") or "")
                ),
                freshness_sources=freshness_sources,
            )
            stored_vector = dict(entry_value.get("freshness_vector") or {})
            changed_keys = [
                key
                for key, value in current_vector.items()
                if stored_vector.get(key) != value
            ]
            if changed_keys:
                invalidated_by.append("freshness_vector_changed")
                public["diagnostics"] = {
                    **dict(public.get("diagnostics") or {}),
                    "freshness_vector_changed_keys": sorted(changed_keys),
                }
        if invalidated_by:
            public["state"] = "expired"
            public["diagnostics"] = {
                **dict(public.get("diagnostics") or {}),
                "invalidated_by": sorted(set(invalidated_by)),
            }
        return public

    if not record_consumer_read:
        return project(entry)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entries = data.setdefault("entries", {})
        stored = entries.get(lock_id)
        if not isinstance(stored, dict):
            return project(entry)
        stored = dict(stored)
        public_before = project(stored)
        metrics = dict(stored.get("consumer_metrics") or {})
        read_count = int(metrics.get("read_count") or 0) + 1
        now = now_utc()
        now_unix = time.time()
        generation = int(stored.get("enrichment_generation") or 0)
        if not metrics.get("first_read_at"):
            metrics["first_read_at"] = now
            metrics["first_read_unix"] = now_unix
            metrics["first_read_state"] = public_before.get("state")
            metrics["first_read_generation"] = generation
        metrics["read_count"] = read_count
        metrics["last_read_at"] = now
        metrics["last_read_unix"] = now_unix
        metrics["last_read_state"] = public_before.get("state")
        metrics["last_read_generation"] = generation
        stored["consumer_metrics"] = metrics
        entries[lock_id] = stored
        return project(stored)

    return _with_store_writer(target, mutate)


def find_recall_lock(
    path: Path | str,
    *,
    prompt: str,
    thread_id: str | None,
    workspace: str | Path,
    topic_epoch: str | None,
    registry_path: Path | str | None = None,
    query_aliases: list[str] | None = None,
) -> dict[str, Any]:
    registry_fp = registry_freshness_fingerprint(Path(registry_path) if registry_path else None)
    lock_id = lock_id_for_route(
        prompt=prompt,
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        registry_freshness=registry_fp,
        query_aliases=query_aliases,
    )
    return read_recall_lock(
        path,
        lock_id,
        topic_epoch=topic_epoch,
        registry_freshness_fingerprint=registry_fp,
    )


def _message_matches_ref(message: dict[str, Any], ref: dict[str, Any]) -> bool:
    message_id = str(message.get("message_id") or message.get("id") or "")
    if ref.get("message_id") and str(ref.get("message_id")) == message_id:
        return True
    turn_id = str(message.get("turn_id") or "")
    if ref.get("turn_id") and str(ref.get("turn_id")) == turn_id:
        return True
    turn_index = str(message.get("turn_index") or "")
    if ref.get("turn_index") and str(ref.get("turn_index")) == turn_index:
        return True
    line = str(message.get("source_line") or "")
    ref_line = ref.get("line") or ref.get("source_line")
    return bool(ref_line and str(ref_line) == line)


def reopen_lock_sources(
    path: Path | str,
    *,
    lock_id: str,
    registry_path: Path | str | None,
    topic_epoch: str | None = None,
    freshness_sources: list[dict[str, Any]] | None = None,
    expected_lock_version: int | None = None,
    max_matches: int = 8,
) -> dict[str, Any]:
    target = Path(path)
    registry_fp = registry_freshness_fingerprint(registry_path) if registry_path else None
    lock = read_recall_lock(
        target,
        lock_id,
        topic_epoch=topic_epoch,
        registry_freshness_fingerprint=registry_fp,
        freshness_sources=freshness_sources,
    )
    if expected_lock_version is not None and _nonnegative_int(lock.get("lock_version")) != max(
        0, int(expected_lock_version)
    ):
        _bump_lock_roi(target, lock_id, reopen_attempt_count=1, wrong_or_stale_route_count=1)
        return {
            "kind": "aippocampus_active_recall_reopen",
            "schema_version": LOCK_SCHEMA_VERSION,
            "lock_id": lock_id,
            "ok": False,
            "state": "superseded",
            "support_level": "scent",
            "source_reopen_required": True,
            "matches": [],
            "errors": [
                {
                    "code": "lock_generation_superseded",
                    "expected_lock_version": max(0, int(expected_lock_version)),
                    "actual_lock_version": _nonnegative_int(lock.get("lock_version")),
                }
            ],
            "source_boundary": {
                "clean_source_reopened": False,
                "lock_material_was_navigation_only": True,
            },
        }
    if lock.get("state") != "ready":
        is_stale = lock.get("state") == "expired" and bool(
            (lock.get("diagnostics") or {}).get("invalidated_by")
        )
        _bump_lock_roi(target, lock_id, reopen_attempt_count=1, wrong_or_stale_route_count=1)
        return {
            "kind": "aippocampus_active_recall_reopen",
            "schema_version": LOCK_SCHEMA_VERSION,
            "lock_id": lock_id,
            "ok": False,
            "state": lock.get("state"),
            "support_level": "scent",
            "source_reopen_required": True,
            "matches": [],
            "errors": [
                {
                    "code": "lock_stale" if is_stale else "lock_not_ready",
                    "state": lock.get("state"),
                    "invalidated_by": (lock.get("diagnostics") or {}).get("invalidated_by") or [],
                }
            ],
        }
    if registry_path is None:
        _bump_lock_roi(target, lock_id, reopen_attempt_count=1, wrong_or_stale_route_count=1)
        return {
            "kind": "aippocampus_active_recall_reopen",
            "schema_version": LOCK_SCHEMA_VERSION,
            "lock_id": lock_id,
            "ok": False,
            "state": lock.get("state"),
            "support_level": "scent",
            "source_reopen_required": True,
            "matches": [],
            "errors": [{"code": "registry_required"}],
        }
    registry = load_registry(Path(registry_path))
    by_thread = {
        str(row.get("thread_key") or ""): row
        for row in registry.get("threads") or []
        if isinstance(row, dict)
    }
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for ref in lock.get("candidate_refs") or []:
        if not isinstance(ref, dict) or not ref.get("thread_key"):
            continue
        entry = by_thread.get(str(ref.get("thread_key")))
        messages_path_value = (entry or {}).get("paths", {}).get("clean_source_messages_jsonl")
        if not messages_path_value:
            errors.append({"code": "clean_source_missing", "thread_key": ref.get("thread_key")})
            continue
        messages_path = Path(str(messages_path_value))
        for message in iter_clean_messages(messages_path):
            if not _message_matches_ref(message, ref):
                continue
            matches.append(
                {
                    "thread_key": ref.get("thread_key"),
                    "message_id": message.get("message_id") or message.get("id"),
                    "turn_id": message.get("turn_id"),
                    "turn_index": message.get("turn_index"),
                    "line": message.get("source_line"),
                    "role": message.get("role"),
                    "phase": message.get("phase") or "",
                    "timestamp": message.get("timestamp"),
                    "support_level": "evidence",
                    "text": str(message.get("text") or ""),
                }
            )
            break
        if len(matches) >= max_matches:
            break
    _bump_lock_roi(
        target,
        lock_id,
        reopen_attempt_count=1,
        source_backed_hit_count=1 if matches else 0,
        wrong_or_stale_route_count=0 if matches else 1,
    )
    return {
        "kind": "aippocampus_active_recall_reopen",
        "schema_version": LOCK_SCHEMA_VERSION,
        "lock_id": lock_id,
        "ok": bool(matches),
        "state": lock.get("state"),
        "support_level": "evidence" if matches else "scent",
        "source_reopen_required": not bool(matches),
        "matches": matches,
        "errors": errors,
        "source_boundary": {
            "clean_source_reopened": bool(matches),
            "lock_material_was_navigation_only": True,
        },
    }


def summarize_lock_roi(path: Path | str) -> dict[str, Any]:
    data = _load_store(Path(path))
    entries = [
        entry
        for entry in (data.get("entries") or {}).values()
        if isinstance(entry, dict)
    ]
    return summarize_lock_roi_entries(
        entries,
        public_lock=_public_lock,
        schema_version=LOCK_SCHEMA_VERSION,
    )
