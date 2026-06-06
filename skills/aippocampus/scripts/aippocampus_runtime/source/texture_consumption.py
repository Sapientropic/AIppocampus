"""Project source-texture rows into safe consumer inputs.

Source texture is intentionally not clean source. This helper gives Dream,
Journey, and correction code one shared way to consume texture as route
material without letting each layer reinvent truth boundaries or leak raw
payloads.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.source.source_texture import (
    SOURCE_TEXTURE_BOUNDARY,
    SOURCE_TEXTURE_KIND,
)

TEXTURE_SIGNAL_KIND = "aippocampus_texture_signal"
CONSUMERS = {"dream", "journey", "correction", "recall"}
SIGNAL_CONSUMER_USES: dict[str, dict[str, str]] = {
    "self_correction_signal": {
        "dream": "dream_seed",
        "journey": "journey_waypoint_hint",
        "correction": "correction_outcome_hint",
        "recall": "silent_route_context",
    },
    "uncertainty_or_frontier_signal": {
        "dream": "prospective_dream_seed",
        "journey": "journey_waypoint_hint",
        "recall": "silent_route_context",
    },
    "affect_marker": {
        "dream": "compensatory_dream_seed",
        "journey": "journey_waypoint_hint",
        "recall": "silent_route_context",
    },
    "abandoned_direction": {
        "dream": "active_imagination_seed",
        "journey": "journey_waypoint_hint",
        "correction": "correction_outcome_hint",
        "recall": "silent_route_context",
    },
    "rejected_route": {
        "dream": "active_imagination_seed",
        "journey": "journey_waypoint_hint",
        "correction": "correction_outcome_hint",
        "recall": "silent_route_context",
    },
    "process_route_note": {
        "dream": "dream_seed",
        "journey": "journey_waypoint_hint",
        "correction": "correction_outcome_hint",
        "recall": "silent_route_context",
    },
    "tool_failure_texture": {
        "dream": "compensatory_dream_seed",
        "journey": "journey_waypoint_hint",
        "correction": "correction_outcome_hint",
        "recall": "silent_route_context",
    },
}
SAFE_SOURCE_REF_KEYS = {
    "ref",
    "turn_ref",
    "thread_key",
    "thread_id",
    "message_id",
    "turn_id",
    "source_id",
    "source_ref",
    "clean_ordinal",
    "source_line",
    "line",
    "user_line",
    "assistant_line",
    "turn_index",
    "title",
    "project_label",
    "role",
    "phase",
    "timestamp",
}
SAFE_EVENT_REF_KEYS = {
    "event_id",
    "source_id",
    "source_ref",
    "turn_index",
    "source_line",
    "line",
    "raw_start_line",
    "raw_end_line",
    "hard_event_kind",
    "event_kind",
    "status",
    "command_class",
    "command_family",
    "target_class",
    "test_target_class",
    "failure_family",
    "critical_operation_family",
    "exit_code",
    "call_ref",
}


def _as_mapping_items(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _safe_ref(item: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in item.items():
        if key not in allowed or value in (None, "", []):
            continue
        out["line" if key == "source_line" else str(key)] = value
    return out


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_ref") or ref.get("line") or ""),
        str(ref.get("event_id") or ""),
    )


def _dedupe_refs(
    items: Iterable[Mapping[str, Any]],
    *,
    allowed: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for item in items:
        ref = _safe_ref(item, allowed)
        key = _ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        out.append(ref)
        if len(out) >= limit:
            break
    return out


def _string_list(value: object, *, limit: int = 8, max_chars: int = 80) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _safe_text(item, max_chars=max_chars)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_text(value: object, *, max_chars: int) -> str:
    sanitized, _policy = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, max_chars)


def _texture_candidates(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nested = row.get("texture_signals") or row.get("source_texture_signals")
    nested_items = _as_mapping_items(nested)
    if nested_items:
        return nested_items
    if row.get("kind") in {SOURCE_TEXTURE_KIND, TEXTURE_SIGNAL_KIND}:
        return [row]
    return []


def project_texture_signal(
    row: Mapping[str, Any],
    *,
    consumer: str,
) -> tuple[dict[str, Any] | None, str]:
    """Return a sanitized consumer signal plus a reason code."""

    if consumer not in CONSUMERS:
        return None, "unsupported_consumer"
    if row.get("kind") != SOURCE_TEXTURE_KIND and row.get("kind") != TEXTURE_SIGNAL_KIND:
        return None, "not_source_texture"
    if str(row.get("truth_boundary") or row.get("texture_boundary") or "") != SOURCE_TEXTURE_BOUNDARY:
        return None, "boundary_mismatch"

    signal_kind = _safe_text(row.get("signal_kind") or row.get("texture_kind") or "", max_chars=80)
    suggested_use = SIGNAL_CONSUMER_USES.get(signal_kind, {}).get(consumer)
    if not suggested_use:
        return None, "consumer_not_enabled"

    source_refs = _dedupe_refs(
        _as_mapping_items(row.get("source_refs")),
        allowed=SAFE_SOURCE_REF_KEYS,
        limit=6,
    )
    event_refs = _dedupe_refs(
        _as_mapping_items(row.get("event_refs")),
        allowed=SAFE_EVENT_REF_KEYS,
        limit=4,
    )
    if not source_refs and not event_refs:
        return None, "missing_safe_refs"

    texture_id = _safe_text(row.get("texture_id") or row.get("signal_id") or "", max_chars=96)
    if not texture_id:
        texture_id = f"texture:{signal_kind}:{len(source_refs)}:{len(event_refs)}"
    signal = {
        "kind": TEXTURE_SIGNAL_KIND,
        "texture_id": texture_id,
        "signal_kind": signal_kind,
        "signal_detail": _safe_text(row.get("signal_detail") or "", max_chars=120),
        "signal_labels": _string_list(row.get("signal_labels"), limit=8),
        "origin": _safe_text(row.get("origin") or "", max_chars=80),
        "suggested_use": suggested_use,
        "texture_boundary": SOURCE_TEXTURE_BOUNDARY,
        "truth_boundary": SOURCE_TEXTURE_BOUNDARY,
        "navigation_only": True,
        "source_reopen_required_before_claim": True,
        "output_authority": "interpretation_input_only",
        "source_refs": source_refs,
        "event_refs": event_refs,
    }
    signal["source_ref_count"] = len(source_refs)
    signal["event_ref_count"] = len(event_refs)
    return {key: value for key, value in signal.items() if value not in (None, "", [], {})}, "selected"


def select_texture_signals(
    rows: Iterable[Mapping[str, Any]],
    *,
    consumer: str,
    limit: int = 12,
) -> dict[str, Any]:
    """Select sanitized source-texture signals for one consumer."""

    selected: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    max_items = max(0, int(limit))
    for row in rows:
        for candidate in _texture_candidates(row):
            signal, reason = project_texture_signal(candidate, consumer=consumer)
            if signal is None:
                reasons[reason] += 1
                continue
            marker = (
                str(signal.get("texture_id") or ""),
                str(signal.get("signal_kind") or ""),
                tuple(
                    sorted(
                        (str(key), str(value))
                        for ref in signal.get("source_refs") or []
                        for key, value in ref.items()
                    )
                ),
            )
            if marker in seen:
                reasons["duplicate"] += 1
                continue
            seen.add(marker)
            if len(selected) >= max_items:
                reasons["limit_exceeded"] += 1
                continue
            selected.append(signal)

    signal_kinds = Counter(str(item.get("signal_kind") or "") for item in selected)
    diagnostics = {
        "consumer": consumer,
        "selected_count": len(selected),
        "signal_kinds": dict(signal_kinds),
        "suppression_reasons": dict(reasons),
        "texture_boundary": SOURCE_TEXTURE_BOUNDARY,
        "raw_text_included": False,
        "raw_tool_payloads_included": False,
        "local_paths_included": False,
    }
    return {"signals": selected, "diagnostics": diagnostics}


def texture_signal_summary(
    signals: Iterable[Mapping[str, Any]],
    *,
    consumer: str,
    suppression_reasons: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    rows = [signal for signal in signals if isinstance(signal, Mapping)]
    return {
        "consumer": consumer,
        "selected_count": len(rows),
        "signal_kinds": dict(Counter(str(row.get("signal_kind") or "") for row in rows)),
        "suggested_uses": dict(Counter(str(row.get("suggested_use") or "") for row in rows)),
        "source_ref_count": sum(len(row.get("source_refs") or []) for row in rows),
        "event_ref_count": sum(len(row.get("event_refs") or []) for row in rows),
        "suppression_reasons": dict(suppression_reasons or {}),
        "texture_boundary": SOURCE_TEXTURE_BOUNDARY,
        "raw_text_included": False,
    }


def texture_signal_source_refs(
    signals: Iterable[Mapping[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    refs: list[Mapping[str, Any]] = []
    for signal in signals:
        refs.extend(_as_mapping_items(signal.get("source_refs")))
    return _dedupe_refs(refs, allowed=SAFE_SOURCE_REF_KEYS, limit=limit)
