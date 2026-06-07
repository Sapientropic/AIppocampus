#!/usr/bin/env python3
"""Source-ref utilities for model-backed Dream findings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import compact_text


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_line") or ref.get("line") or ""),
    )


def clean_source_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    clean = {
        "thread_key": ref.get("thread_key") or ref.get("thread_id"),
        "message_id": ref.get("message_id"),
        "turn_id": ref.get("turn_id"),
        "line": ref.get("line") or ref.get("source_line"),
        "turn_index": ref.get("turn_index"),
        "project_label": ref.get("project_label"),
        "title": ref.get("title"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def source_ref_inventory(pack: Mapping[str, Any]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in pack.get("source_refs") or []:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        inventory.append({"source_ref_id": f"sr{len(inventory)}", **clean_source_ref(item)})
    return inventory


def source_refs_by_id(pack: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("source_ref_id")): {key: value for key, value in item.items() if key != "source_ref_id"}
        for item in source_ref_inventory(pack)
    }


def resolve_refs(source_ref_ids: object, by_id: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(source_ref_ids, str):
        raw_ids = [source_ref_ids]
    elif isinstance(source_ref_ids, list):
        raw_ids = source_ref_ids
    else:
        raw_ids = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw_id in raw_ids:
        ref = by_id.get(str(raw_id))
        if not ref:
            continue
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append(dict(ref))
    return refs


def bridge_claims_from_candidate(
    candidate: Mapping[str, Any],
    *,
    by_id: Mapping[str, dict[str, Any]],
    fallback_refs: list[dict[str, Any]],  # Reserved for callers that need explicit legacy fallback.
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in candidate.get("bridge_claims") or []:
        if not isinstance(item, Mapping):
            continue
        refs = resolve_refs(item.get("source_ref_ids"), by_id)
        claims.append({"claim": compact_text(str(item.get("claim") or ""), 240), "source_refs": refs[:8]})
    return claims


def has_source_refs(row: Mapping[str, Any]) -> bool:
    refs = row.get("source_refs")
    if not isinstance(refs, list):
        return False
    return any(isinstance(ref, Mapping) and any(source_ref_key(ref)) for ref in refs)
