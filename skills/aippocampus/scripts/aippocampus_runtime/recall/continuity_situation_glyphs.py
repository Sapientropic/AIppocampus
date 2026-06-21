#!/usr/bin/env python3
"""Direction-only situation glyph projection for continuity-domain signals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.authority import (
    ACTION_DIRECTION_ONLY,
    ACTION_IGNORE_OR_BLOCKED,
    TRUST_IGNORE,
    TRUST_SEMANTIC_HINT,
)

CONTINUITY_DOMAIN_SCHEMA_VERSION = 1
SITUATION_GLYPH_KIND = "aippocampus_situation_glyph"
HARD_BLOCKING_BOUNDARY_EFFECTS = {"block_hook", "suppress_domain"}

SIGNAL_PRODUCERS = {
    "source_texture",
    "dream",
    "journey",
    "hexagram",
    "cognitive_map",
    "navigation_potential",
    "working_memory",
    "continuity_domain",
}
SIGNAL_PRODUCER_BOUNDARIES = {
    "dream": "dream_hypothesis_not_source_fact",
    "hexagram": "hexagram_atmosphere_not_fact",
    "cognitive_map": "cognitive_map_route_not_source_fact",
    "journey": "journey_route_not_source_fact",
    "source_texture": "texture_signal_not_source_fact",
    "navigation_potential": "navigation_not_truth",
    "working_memory": "working_memory_candidate_not_source_fact",
    "continuity_domain": "domain_pointer_not_source_fact",
}


def _stable_id(*parts: Any, prefix: str, length: int = 20) -> str:
    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _safe_text(value: Any, chars: int = 220) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:chars]


def _safe_list(values: Any, *, limit: int = 12, chars: int = 80) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, Iterable):
        raw_values = list(values)
    else:
        raw_values = [values]
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = _safe_text(value, chars).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(ref.get("conversation_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("role") or ""),
        str(ref.get("created_at") or ""),
        str(ref.get("source_path") or ref.get("path") or ""),
    )


def _dedupe_refs(refs: Iterable[dict[str, Any]], *, limit: int = 24) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for ref in refs:
        key = _ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
        if len(deduped) >= limit:
            break
    return deduped


def normalize_continuity_signal(row: Mapping[str, Any]) -> dict[str, Any] | None:
    producer = _safe_text(row.get("producer") or row.get("source") or row.get("surface"), 80)
    if producer not in SIGNAL_PRODUCERS:
        return None
    signal_kind = _safe_text(row.get("signal_kind") or row.get("kind") or producer, 100)
    source_refs = safe_source_refs(row.get("source_refs") or row.get("event_refs"))
    signal_id = _safe_text(row.get("signal_id"), 100) or _stable_id(
        producer,
        signal_kind,
        row.get("signal_labels") or row.get("labels"),
        source_refs,
        prefix="sig",
    )
    signal = {
        "signal_id": signal_id,
        "producer": producer,
        "signal_kind": signal_kind,
        "signal_detail": _safe_text(row.get("signal_detail") or row.get("detail") or "", 220),
        "signal_labels": _safe_list(row.get("signal_labels") or row.get("labels"), limit=12),
        "source_refs": source_refs[:8],
        "action_grammar": ACTION_DIRECTION_ONLY,
        "trust_level": TRUST_SEMANTIC_HINT,
        "memory_surface": "memory_atmosphere",
        "foreground_eligible": False,
        "truth_boundary": SIGNAL_PRODUCER_BOUNDARIES.get(producer, "signal_not_source_fact"),
        "cannot_claim": [
            "signal_is_fact",
            "signal_can_support_exact_claim",
            "signal_replaces_source_reopen",
        ],
    }
    return redact_sensitive_values(redact_private_paths(signal))


def _ordered_pathlet_fingerprint(pathlets: Sequence[Mapping[str, Any]]) -> str:
    ordered = []
    for pathlet in pathlets:
        ordered.append(
            [
                pathlet.get("pathlet_id"),
                [_ref_key(ref) for ref in pathlet.get("ordered_source_refs") or [] if isinstance(ref, Mapping)],
            ]
        )
    return _stable_id(ordered, prefix="pathorder")


def project_situation_glyph(
    *,
    signals: Sequence[Mapping[str, Any]],
    pathlets: Sequence[Mapping[str, Any]] | None = None,
    pinned_boundaries: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = [
        signal
        for row in signals
        if isinstance(row, Mapping)
        for signal in [normalize_continuity_signal(row)]
        if signal is not None
    ]
    pathlet_rows = [dict(row) for row in pathlets or [] if isinstance(row, Mapping)]
    boundary_rows = [dict(row) for row in pinned_boundaries or [] if isinstance(row, Mapping)]
    blocking = [
        row
        for row in boundary_rows
        if str(row.get("effect") or "") in HARD_BLOCKING_BOUNDARY_EFFECTS | {"redirect"}
    ]
    action = ACTION_IGNORE_OR_BLOCKED if blocking else ACTION_DIRECTION_ONLY
    status = "redirected_by_boundary" if blocking else "ok"
    labels = _safe_list(
        [
            label
            for signal in normalized
            for label in signal.get("signal_labels") or [signal.get("signal_kind")]
        ],
        limit=12,
    )
    path_order = _ordered_pathlet_fingerprint(pathlet_rows)
    glyph_id = _stable_id(
        [signal.get("signal_id") for signal in normalized],
        path_order,
        [(boundary.get("pin_id"), boundary.get("effect")) for boundary in boundary_rows],
        prefix="glyph",
    )
    source_refs = _dedupe_refs(
        [ref for signal in normalized for ref in signal.get("source_refs") or []],
        limit=12,
    )
    glyph = {
        "kind": SITUATION_GLYPH_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "glyph_id": glyph_id,
        "status": status,
        "action_grammar": action,
        "trust_level": TRUST_IGNORE if blocking else TRUST_SEMANTIC_HINT,
        "memory_surface": "memory_atmosphere",
        "foreground_eligible": False,
        "atmosphere_labels": labels,
        "producer_counts": {
            producer: sum(1 for signal in normalized if signal.get("producer") == producer)
            for producer in sorted({str(signal.get("producer") or "") for signal in normalized})
        },
        "source_refs": source_refs,
        "pathlet_ids": [row.get("pathlet_id") for row in pathlet_rows if row.get("pathlet_id")],
        "boundary_redirects": [
            {
                "kind": row.get("kind") or row.get("boundary_kind"),
                "effect": row.get("effect"),
                "strength": row.get("strength"),
            }
            for row in blocking
        ],
        "truth_boundary": "situation_glyph_is_atmosphere_not_source_fact",
        "cannot_claim": [
            "glyph_is_fact",
            "glyph_is_user_profile",
            "glyph_predicts_future",
            "glyph_overrides_clean_source",
        ],
        "diagnostics": {
            "signal_count": len(normalized),
            "pathlet_count": len(pathlet_rows),
            "pathlet_order_fingerprint": path_order,
            "pathlet_order_sensitive": True,
            "pinned_boundary_count": len(boundary_rows),
        },
    }
    return redact_sensitive_values(redact_private_paths(glyph))
