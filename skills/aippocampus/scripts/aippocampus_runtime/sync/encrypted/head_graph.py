#!/usr/bin/env python3
"""Encrypted sync head graph and divergent-head diagnostics."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc, safe_path_name
from aippocampus_runtime.sync import bundle as sync_bundle

ENCRYPTED_HEAD_CONFLICT_DIR = ".sync-conflicts/encrypted-heads"
HEAD_GRAPH_SCHEMA_VERSION = 1
SENDER_TRUST_MODEL = "trusted_recipient_can_author_bundle"

QUARANTINE_PATH_KINDS = {
    "registry/semantic_triggers.jsonl": "semantic_trigger",
    "registry/semantic_cues.jsonl": "semantic_trigger",
    "registry/working_memory.jsonl": "activation_or_working_memory",
    "registry/cognitive_map.json": "strategy_like",
    "registry/concept_graph.json": "strategy_like",
    "registry/subconscious_edges.jsonl": "dream_or_subconscious",
    "registry/subconscious_jobs.jsonl": "dream_or_subconscious",
    "registry/promotion_candidates.jsonl": "dream_or_subconscious",
    "registry/subconscious_state.json": "dream_or_subconscious",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def head_id_from_state(state: dict[str, Any]) -> str:
    return str(state.get("head_id") or state.get("manifest_hash") or "")


def _parent_heads_from_state(state: dict[str, Any]) -> list[str]:
    values = state.get("parent_heads")
    if isinstance(values, list):
        return [str(value) for value in values if str(value or "").strip()]
    parent = state.get("parent_manifest_hash")
    return [str(parent)] if parent else []


def sender_trust_boundary() -> dict[str, Any]:
    # Age proves that a configured recipient can decrypt the bundle; it does not
    # prove which trusted device authored it. Keep this named boundary visible
    # until signed head metadata and trust-root rotation exist.
    return {
        "model": SENDER_TRUST_MODEL,
        "trusted_recipient_can_author_bundle": True,
        "sender_authenticated": False,
        "manifest_signing_enabled": False,
        "auto_accept_multi_writer": False,
        "diagnostic": "age recipient trust decrypts bundles but does not authenticate the sender",
    }


def head_summary_from_manifest(inner_manifest: dict[str, Any]) -> dict[str, Any]:
    head_graph = inner_manifest.get("head_graph")
    graph = head_graph if isinstance(head_graph, dict) else {}
    parent_heads = graph.get("parent_heads") or inner_manifest.get("parent_heads") or []
    return {
        "head_id": str(
            inner_manifest.get("head_id")
            or graph.get("head_id")
            or inner_manifest.get("manifest_hash")
            or ""
        ),
        "manifest_hash": inner_manifest.get("manifest_hash"),
        "manifest_revision": inner_manifest.get("manifest_revision"),
        "parent_manifest_hash": inner_manifest.get("parent_manifest_hash"),
        "parent_heads": [str(value) for value in parent_heads if str(value or "").strip()],
        "device_id": graph.get("device_id") or inner_manifest.get("source_device_id"),
        "source_device_id": inner_manifest.get("source_device_id"),
        "logical_counter": graph.get("logical_counter") or inner_manifest.get("logical_counter"),
        "sender_trust": inner_manifest.get("sender_trust") or sender_trust_boundary(),
    }


def head_summary_from_state(state: dict[str, Any]) -> dict[str, Any]:
    accepted = state.get("accepted_head")
    if isinstance(accepted, dict):
        return dict(accepted)
    return {
        "head_id": head_id_from_state(state),
        "manifest_hash": state.get("manifest_hash"),
        "manifest_revision": state.get("manifest_revision"),
        "parent_manifest_hash": state.get("parent_manifest_hash"),
        "parent_heads": _parent_heads_from_state(state),
        "device_id": state.get("source_device_id"),
        "source_device_id": state.get("source_device_id"),
        "logical_counter": None,
        "sender_trust": sender_trust_boundary(),
    }


def _next_logical_counter(previous_state: dict[str, Any], source_device_id: str) -> int:
    counters = previous_state.get("device_counters")
    if not isinstance(counters, dict):
        counters = {}
    try:
        return int(counters.get(source_device_id) or 0) + 1
    except (TypeError, ValueError):
        return 1


def build_head_graph(
    *,
    previous_state: dict[str, Any],
    source_device_id: str,
    parent_manifest_hash: str | None,
) -> dict[str, Any]:
    parent_head = head_id_from_state(previous_state)
    parent_heads = [parent_head] if parent_head else []
    logical_counter = _next_logical_counter(previous_state, source_device_id)
    seed = uuid.uuid4().hex
    head_id = "head_" + _sha256_bytes(
        "\n".join(
            [
                source_device_id,
                str(logical_counter),
                "|".join(parent_heads),
                str(parent_manifest_hash or ""),
                seed,
            ]
        ).encode("utf-8")
    )[:24]
    return {
        "schema_version": HEAD_GRAPH_SCHEMA_VERSION,
        "head_id": head_id,
        "device_id": source_device_id,
        "parent_heads": parent_heads,
        "parent_manifest_hash": parent_manifest_hash,
        "logical_counter": logical_counter,
    }


def quarantine_plan_for_conflicting_head(inner_manifest: dict[str, Any]) -> dict[str, Any]:
    # Divergent encrypted heads must not poison the whole vault. Only generated
    # activation/dream/strategy surfaces from the conflicting head are
    # quarantined; clean-source remains source-backed and eligible for manual
    # resolution.
    quarantined: list[str] = []
    by_kind: dict[str, int] = {}
    source_backed_preserved = False
    for record in inner_manifest.get("objects") or []:
        logical_path = str(record.get("logical_path") or "").replace("\\", "/")
        kind = QUARANTINE_PATH_KINDS.get(logical_path)
        if kind:
            quarantined.append(logical_path)
            by_kind[kind] = by_kind.get(kind, 0) + 1
            continue
        if "/clean-source/" in f"/{logical_path}":
            source_backed_preserved = True
    return {
        "status": "quarantined_conflicting_head",
        "conflicting_head_id": inner_manifest.get("head_id") or inner_manifest.get("manifest_hash"),
        "vault_wide_demote": False,
        "clean_source_mutation_allowed": False,
        "source_backed_paths_preserved": source_backed_preserved,
        "quarantined_path_count": len(quarantined),
        "quarantined_logical_paths": sorted(quarantined),
        "quarantined_by_kind": by_kind,
        "reason": (
            "only activation, dream, semantic-trigger, and strategy-like rows from "
            "the conflicting head are quarantined"
        ),
    }


def _conflict_dir(target_registry: Path, incoming_head_id: str) -> Path:
    timestamp = now_utc().replace(":", "").replace("+", "Z")
    suffix = safe_path_name(incoming_head_id or "head", "head")[:40]
    return target_registry / ENCRYPTED_HEAD_CONFLICT_DIR / f"{timestamp}-{suffix}"


def preserve_divergent_heads(
    target_registry: Path,
    *,
    current_state: dict[str, Any],
    incoming_manifest: dict[str, Any],
    quarantine: dict[str, Any],
) -> dict[str, Any]:
    accepted_head = head_summary_from_state(current_state)
    incoming_head = head_summary_from_manifest(incoming_manifest)
    conflict_dir = _conflict_dir(target_registry, str(incoming_head.get("head_id") or "head"))
    conflict_dir.mkdir(parents=True, exist_ok=True)
    conflict_report = {
        "kind": "aippocampus_encrypted_sync_divergent_head_conflict",
        "schema_version": 1,
        "created_at": now_utc(),
        "accepted_head": accepted_head,
        "incoming_head": incoming_head,
        "provenance_quarantine": quarantine,
        "sender_trust": incoming_head.get("sender_trust") or sender_trust_boundary(),
        "auto_accept_allowed": False,
        "cannot_claim": [
            "sender_authentication_exists",
            "divergent_heads_were_merged",
            "vault_wide_demotion_was_required",
            "live_provider_multi_writer_quality",
        ],
    }
    sync_bundle.save_json(conflict_dir / "accepted-head.json", accepted_head)
    sync_bundle.save_json(conflict_dir / "incoming-head.json", incoming_head)
    sync_bundle.save_json(conflict_dir / "divergent-heads.json", conflict_report)
    return {
        "conflict_dir": str(conflict_dir),
        "accepted_head": accepted_head,
        "incoming_head": incoming_head,
    }


def heads_share_parent(current_state: dict[str, Any], incoming_manifest: dict[str, Any]) -> bool:
    accepted = head_summary_from_state(current_state)
    current_parents = set(str(value) for value in accepted.get("parent_heads") or [])
    incoming_parents = set(str(value) for value in incoming_manifest.get("parent_heads") or [])
    if current_parents and incoming_parents and current_parents.intersection(incoming_parents):
        return True
    return bool(
        incoming_manifest.get("parent_manifest_hash")
        and accepted.get("parent_manifest_hash")
        and incoming_manifest.get("parent_manifest_hash") == accepted.get("parent_manifest_hash")
    )
