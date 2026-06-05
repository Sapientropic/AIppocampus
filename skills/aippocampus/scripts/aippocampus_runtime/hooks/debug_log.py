"""Explicit prompt-hook debug logging with write-boundary redaction."""

from __future__ import annotations

import json
import math
import secrets
from pathlib import Path
from typing import Any

from aippocampus_runtime import core as runtime_core
from aippocampus_runtime.ops import log_retention

PROMPT_HOOK_LOG_NAME = "aippocampus_prompt_hook.jsonl"
PROMPT_HOOK_STATUS_NAME = "aippocampus_prompt_hook_last_status.json"

PUBLIC_DECISIONS = {"skip", "scent", "evidence"}
PUBLIC_CONFIDENCES = {"low", "medium", "high"}
PUBLIC_MEMORY_SURFACES = {"candidate", "no_memory", "scent", "source_backed_evidence"}
PUBLIC_CACHE_STATUSES = {
    "disabled",
    "error",
    "hit",
    "miss",
    "not_used",
    "related_hit",
    "skipped",
    "unavailable",
}
PUBLIC_WRITE_STATUSES = {"disabled", "error", "skipped", "unavailable", "written"}
PUBLIC_WARM_STATUSES = {
    "disabled",
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
    "written",
}
PUBLIC_SUPPORT_LEVELS = {"candidate", "evidence", "scent"}
PUBLIC_PROVENANCE_CLASSES = {
    "cached_warm_card",
    "cognitive_map_route",
    "deterministic_cue",
    "source_backed_reopen",
    "warm_scout_proposal",
    "working_memory_model",
    "working_memory_source",
}
PUBLIC_VISIBILITIES = {
    "active_gentle_nudge",
    "deep_archival_recall",
    "silent_tuning",
    "source_backed_recall_card",
}
PUBLIC_SOURCE_VALIDATION_STATUSES = {
    "missing_source_ref",
    "missing_source_refs",
    "supported",
    "unsupported",
    "unverified_no_source_index",
}


def default_prompt_hook_log_path() -> Path:
    return runtime_core.aippocampus_registry_dir() / PROMPT_HOOK_LOG_NAME


def default_prompt_hook_status_path() -> Path:
    return runtime_core.aippocampus_registry_dir() / PROMPT_HOOK_STATUS_NAME


def _new_audit_event_id() -> str:
    return "ph_" + secrets.token_hex(8)


def _event_id_value(value: Any) -> str:
    text = str(value or "").strip()
    suffix = text[3:]
    if (
        text.startswith("ph_")
        and len(suffix) == 16
        and all(ch in "0123456789abcdef" for ch in suffix)
    ):
        return text
    return "ph_unavailable"


def _timestamp_value(value: Any) -> str | None:
    text = str(value or "").strip()
    allowed = set("0123456789TtZz:+-. ")
    if 8 <= len(text) <= 40 and all(ch in allowed for ch in text):
        return text
    return None


def _enum_value(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _float_value(value: Any) -> float | None:
    try:
        number = float(str(value or "0"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(max(number, 0.0), 3)


def _count_map(value: Any, *, allowed: set[str] | None = None) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key, raw_count in value.items():
        text = str(key or "").strip()
        if not text:
            continue
        if allowed is not None and text not in allowed:
            continue
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            counts[text] = count
    return counts


def _int_value(value: Any) -> int:
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(count, 0)


def _last_jsonl_event(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                last = parsed
    return last


def _memory_surface(
    *,
    decision: str,
    support_counts: dict[str, int],
    candidate_thread_count: int,
    evidence_count: int,
    working_memory_count: int,
    cognitive_map_count: int,
) -> str:
    if support_counts.get("evidence", 0) or evidence_count:
        return "source_backed_evidence"
    if support_counts.get("candidate", 0) or candidate_thread_count:
        return "candidate"
    if support_counts.get("scent", 0) or working_memory_count or cognitive_map_count:
        return "scent"
    return "no_memory" if decision == "skip" else "scent"


def _privacy_boundary() -> dict[str, bool]:
    return {
        "raw_prompt_text_emitted": False,
        "raw_cards_emitted": False,
        "raw_source_text_emitted": False,
        "session_or_turn_id_emitted": False,
        "local_path_emitted": False,
    }


def _status_base(*, status: str, source: str, artifact_name: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "aippocampus_prompt_hook_audit_status",
        "status": status,
        "source": source,
        "artifact_name": artifact_name,
        "privacy_boundary": _privacy_boundary(),
    }
    if source == "debug_log":
        base["log_name"] = artifact_name
    elif source == "last_status":
        base["status_name"] = artifact_name
    return base


def _public_cache(value: Any) -> dict[str, Any]:
    cache = value if isinstance(value, dict) else {}
    return {
        "status": _enum_value(cache.get("status"), PUBLIC_CACHE_STATUSES, "unavailable"),
        "topic_epoch_present": bool(cache.get("topic_epoch_present") or cache.get("topic_epoch")),
        "card_count": _int_value(cache.get("card_count")),
        "write_status": _enum_value(
            cache.get("write_status"),
            PUBLIC_WRITE_STATUSES,
            "unavailable",
        ),
    }


def _public_warm_background(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "status": _enum_value(value.get("status"), PUBLIC_WARM_STATUSES, "unavailable"),
        "spawned": value.get("spawned") is True,
    }


def _public_ambient_summary(value: Any) -> dict[str, Any]:
    ambient = value if isinstance(value, dict) else {}
    return {
        "card_count": _int_value(ambient.get("card_count")),
        "source_reopen_required_count": _int_value(
            ambient.get("source_reopen_required_count")
        ),
        "cache": _public_cache(ambient.get("cache") or ambient.get("cache_status")),
        "warm_background": _public_warm_background(ambient.get("warm_background")),
        "visibility_counts": _count_map(
            ambient.get("visibility_counts"),
            allowed=PUBLIC_VISIBILITIES,
        ),
        "provenance_counts": _count_map(
            ambient.get("provenance_counts"),
            allowed=PUBLIC_PROVENANCE_CLASSES,
        ),
        "support_level_counts": _count_map(
            ambient.get("support_level_counts"),
            allowed=PUBLIC_SUPPORT_LEVELS,
        ),
        "source_validation_statuses": _count_map(
            ambient.get("source_validation_statuses"),
            allowed=PUBLIC_SOURCE_VALIDATION_STATUSES,
        ),
    }


def _event_from_result(result: dict[str, Any]) -> dict[str, Any]:
    from aippocampus_runtime.recall.prompt_context_render import ambient_debug_summary  # noqa: I001, PLC0415

    ambient = _public_ambient_summary(ambient_debug_summary(result))
    event = {
        "timestamp": runtime_core.now_utc(),
        "decision": _enum_value(result.get("decision"), PUBLIC_DECISIONS, "skip"),
        "score": _float_value(result.get("score")),
        "confidence": _enum_value(result.get("confidence"), PUBLIC_CONFIDENCES, "low"),
        "candidate_count": len(result.get("candidates") or []),
        "evidence_count": len(result.get("evidence") or []),
        "working_memory_count": len(result.get("working_memory") or []),
        "cognitive_map_count": len(result.get("cognitive_map") or []),
        "ambient_recall": ambient,
        "elapsed_ms": _float_value(result.get("elapsed_ms")),
    }
    event["audit_event_id"] = _new_audit_event_id()
    return event


def _project_last_prompt_hook(event: dict[str, Any]) -> dict[str, Any]:
    ambient = _public_ambient_summary(event.get("ambient_recall"))
    cache = _public_cache(ambient.get("cache"))
    warm_background = _public_warm_background(ambient.get("warm_background"))
    support_counts = _count_map(
        ambient.get("support_level_counts"),
        allowed=PUBLIC_SUPPORT_LEVELS,
    )
    provenance_counts = _count_map(
        ambient.get("provenance_counts"),
        allowed=PUBLIC_PROVENANCE_CLASSES,
    )
    visibility_counts = _count_map(
        ambient.get("visibility_counts"),
        allowed=PUBLIC_VISIBILITIES,
    )
    validation_statuses = _count_map(
        ambient.get("source_validation_statuses"),
        allowed=PUBLIC_SOURCE_VALIDATION_STATUSES,
    )
    candidate_thread_count = len(event.get("candidate_threads") or [])
    candidate_count = _int_value(event.get("candidate_count")) or candidate_thread_count
    evidence_count = len(event.get("evidence") or [])
    evidence_count = _int_value(event.get("evidence_count")) or evidence_count
    working_memory_count = len(event.get("working_memory") or [])
    working_memory_count = _int_value(event.get("working_memory_count")) or working_memory_count
    cognitive_map_count = len(event.get("cognitive_map") or [])
    cognitive_map_count = _int_value(event.get("cognitive_map_count")) or cognitive_map_count
    decision = _enum_value(event.get("decision"), PUBLIC_DECISIONS, "skip")

    return {
        "event_id": _event_id_value(event.get("audit_event_id")),
        "timestamp": _timestamp_value(event.get("timestamp")),
        "decision": decision,
        "score": _float_value(event.get("score")),
        "confidence": _enum_value(event.get("confidence"), PUBLIC_CONFIDENCES, "low"),
        "elapsed_ms": _float_value(event.get("elapsed_ms")),
        "memory_surface": _memory_surface(
            decision=decision,
            support_counts=support_counts,
            candidate_thread_count=candidate_count,
            evidence_count=evidence_count,
            working_memory_count=working_memory_count,
            cognitive_map_count=cognitive_map_count,
        ),
        "card_count": _int_value(ambient.get("card_count")),
        "source_backed_count": _int_value(support_counts.get("evidence") or evidence_count),
        "candidate_count": _int_value(support_counts.get("candidate") or candidate_count),
        "scent_count": _int_value(
            support_counts.get("scent") or working_memory_count or cognitive_map_count
        ),
        "wayfinding_count": _int_value(
            provenance_counts.get("cognitive_map_route") or cognitive_map_count
        ),
        "source_reopen_required_count": _int_value(
            ambient.get("source_reopen_required_count")
        ),
        "cache": {
            "status": cache.get("status"),
            "topic_epoch_present": cache.get("topic_epoch_present"),
            "card_count": cache.get("card_count"),
            "write_status": cache.get("write_status"),
        },
        "warm_background": {
            "status": warm_background.get("status"),
            "spawned": warm_background.get("spawned"),
        }
        if warm_background
        else None,
        "visibility_counts": visibility_counts,
        "provenance_counts": provenance_counts,
        "support_level_counts": support_counts,
        "source_validation_statuses": validation_statuses,
    }


def _project_stored_last_prompt_hook(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    warm_background = _public_warm_background(value.get("warm_background"))
    projected = {
        "event_id": _event_id_value(value.get("event_id")),
        "timestamp": _timestamp_value(value.get("timestamp")),
        "decision": _enum_value(value.get("decision"), PUBLIC_DECISIONS, "skip"),
        "score": _float_value(value.get("score")),
        "confidence": _enum_value(value.get("confidence"), PUBLIC_CONFIDENCES, "low"),
        "elapsed_ms": _float_value(value.get("elapsed_ms")),
        "memory_surface": _enum_value(
            value.get("memory_surface"),
            PUBLIC_MEMORY_SURFACES,
            "no_memory",
        ),
        "card_count": _int_value(value.get("card_count")),
        "source_backed_count": _int_value(value.get("source_backed_count")),
        "candidate_count": _int_value(value.get("candidate_count")),
        "scent_count": _int_value(value.get("scent_count")),
        "wayfinding_count": _int_value(value.get("wayfinding_count")),
        "source_reopen_required_count": _int_value(value.get("source_reopen_required_count")),
        "cache": _public_cache(value.get("cache")),
        "warm_background": warm_background,
        "visibility_counts": _count_map(
            value.get("visibility_counts"),
            allowed=PUBLIC_VISIBILITIES,
        ),
        "provenance_counts": _count_map(
            value.get("provenance_counts"),
            allowed=PUBLIC_PROVENANCE_CLASSES,
        ),
        "support_level_counts": _count_map(
            value.get("support_level_counts"),
            allowed=PUBLIC_SUPPORT_LEVELS,
        ),
        "source_validation_statuses": _count_map(
            value.get("source_validation_statuses"),
            allowed=PUBLIC_SOURCE_VALIDATION_STATUSES,
        ),
    }
    return projected


def _status_from_event(*, event: dict[str, Any], source: str, artifact_name: str) -> dict[str, Any]:
    base = _status_base(status="found", source=source, artifact_name=artifact_name)
    base["last_prompt_hook"] = _project_last_prompt_hook(event)
    return runtime_core.sanitize_external_model_payload(base)


def _status_from_status_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    latest = _project_stored_last_prompt_hook(parsed.get("last_prompt_hook"))
    if latest is None:
        return None
    base = _status_base(status="found", source="last_status", artifact_name=path.name)
    base["last_prompt_hook"] = latest
    return runtime_core.sanitize_external_model_payload(base)


def prompt_hook_audit_status(
    log_path: Path | None = None,
    *,
    status_path: Path | None = None,
) -> dict[str, Any]:
    """Return a public-safe summary of the latest prompt-hook memory injection.

    The default last-status file is written on every prompt-hook run and stores
    only this projection. Verbose debug JSONL remains opt-in and may contain
    sanitized thread ids or source locators; this status projection is stricter:
    it emits counts, buckets, and a redacted event id, never raw prompt text,
    card text, source titles, session ids, turn ids, snippets, or local paths.
    """

    status_artifact = status_path or default_prompt_hook_status_path()
    if log_path is None:
        stored = _status_from_status_file(status_artifact)
        if stored is not None:
            return stored
        if status_path is not None:
            return _status_base(
                status="no_status",
                source="last_status",
                artifact_name=status_artifact.name,
            )

    path = log_path or default_prompt_hook_log_path()
    event = _last_jsonl_event(path)
    if event is None:
        if log_path is None:
            base = _status_base(
                status="no_audit_status",
                source="last_status",
                artifact_name=status_artifact.name,
            )
            base["debug_log_name"] = path.name
            return base
        return _status_base(status="no_log", source="debug_log", artifact_name=path.name)

    return _status_from_event(event=event, source="debug_log", artifact_name=path.name)


def write_prompt_hook_audit_status(
    result: dict[str, Any],
    *,
    status_path: Path | None = None,
) -> None:
    """Persist the tiny default audit surface for the latest prompt hook.

    This is intentionally separate from verbose debug logging. It lets a user
    audit the last prompt without enabling raw-ish local JSONL traces, while
    still preserving fail-open hook behavior when the status write fails.
    """

    path = status_path or default_prompt_hook_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = _event_from_result(result)
    payload = _status_from_event(event=event, source="last_status", artifact_name=path.name)
    safe_payload = runtime_core.sanitize_external_model_payload(payload)
    # Best-effort status only: readers treat malformed JSON as no status, so a
    # direct overwrite is sufficient without widening the trusted writer surface.
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(safe_payload, ensure_ascii=False, indent=2) + "\n")


def write_debug_log(
    result: dict[str, Any],
    *,
    hook_input: dict[str, Any] | None = None,
    log_path: Path | None = None,
    include_skip: bool = False,
) -> None:
    if result.get("decision") == "skip" and not include_skip:
        return
    from aippocampus_runtime.recall.prompt_context_render import ambient_debug_summary  # noqa: I001, PLC0415

    # Verbose debug logs keep local routing details, but not hook session ids.
    del hook_input
    path = log_path or default_prompt_hook_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    ambient_summary = ambient_debug_summary(result)
    semantic_gate = result.get("semantic_gate") or {}
    semantic_debug_keys = (
        "available",
        "decision",
        "confidence",
        "cached",
        "query_aliases",
        "availability_reason",
        "diagnostic",
        "elapsed_ms",
        "timeout",
        "budget",
        "error_buckets",
    )
    event = {
        "timestamp": runtime_core.now_utc(),
        "decision": result.get("decision"),
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "query_terms": result.get("query_terms"),
        "concept_expansions": [
            {"term": item.get("term"), "score": item.get("score"), "depth": item.get("depth")}
            for item in result.get("concept_expansions", [])[:5]
        ],
        "cognitive_map": [
            {
                "route_id": item.get("route_id"),
                "landmarks": item.get("landmark_labels"),
                "matched_cues": item.get("matched_cues"),
                "thread_keys": item.get("thread_keys"),
                "score": item.get("score"),
            }
            for item in result.get("cognitive_map", [])[:4]
        ],
        "candidate_threads": [
            {"thread_key": item.get("thread_key"), "title": item.get("title"), "score": item.get("score")}
            for item in result.get("candidates", [])[:3]
        ],
        "working_memory": [
            {"title": item.get("title"), "route": item.get("route"), "score": item.get("score")}
            for item in result.get("working_memory", [])[:3]
        ],
        "semantic_gate": {**{key: semantic_gate.get(key) for key in semantic_debug_keys}, "aliases": semantic_gate.get("query_aliases")}
        if semantic_gate
        else None,
        "evidence": [
            {"thread_key": item.get("thread_key"), "line": item.get("line"), "phase": item.get("phase")}
            for item in result.get("evidence", [])[:5]
        ],
        "ambient_recall": ambient_summary,
        "elapsed_ms": result.get("elapsed_ms"),
    }
    event["audit_event_id"] = _new_audit_event_id()
    # Redact only at the write boundary; recall scoring still uses raw terms.
    safe_event = runtime_core.sanitize_external_model_payload(event)
    log_retention.append_text_with_rotation(path, json.dumps(safe_event, ensure_ascii=False) + "\n")
