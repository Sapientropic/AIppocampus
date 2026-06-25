"""Subconscious staged-edge ingress for the navigation concept graph."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation import concept_graph_edge_policy as edge_policy
from aippocampus_runtime.navigation.associations import normalize_term
from aippocampus_runtime.navigation.concept_graph_term_quality import (
    ConceptTermQualityTracker,
    TermQualityContext,
)
from aippocampus_runtime.navigation.concept_graph_topology_quality import (
    assess_subconscious_hub_quality,
)
from aippocampus_runtime.navigation.concept_lifecycle import (
    lifecycle_decision,
    safe_edge_type,
    source_ref_identity,
    source_ref_thread_keys,
    strongest_lifecycle_signal,
)
from aippocampus_runtime.source.io_kernel import iter_jsonl_dict_rows

UpsertConcept = Callable[..., str | None]
UpsertEdge = Callable[..., None]


def _stable_slice_key(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"subconscious:{digest}"


def iter_concept_graph_rows(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    yield from iter_jsonl_dict_rows(path)


def collect_subconscious_edges(
    con: sqlite3.Connection,
    staging_path: Path | None,
    *,
    term_quality: ConceptTermQualityTracker,
    upsert_concept: UpsertConcept,
    upsert_edge: UpsertEdge,
) -> tuple[int, dict[str, Any]]:
    """Materialize subconscious edge staging rows after quality gates.

    This owner intentionally runs term quality first and topology quality after
    grouping. Term quality prevents bad labels from becoming nodes; topology
    quality parks project-like hub overflow edges while leaving the project
    concept available for healthy orientation routes.
    """

    if not staging_path or not staging_path.exists():
        return 0, {}
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in iter_concept_graph_rows(staging_path):
        if item.get("kind") != "aippocampus_subconscious_edge":
            continue
        src = str(item.get("src") or "")
        dst = str(item.get("dst") or "")
        refs = [ref for ref in item.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            continue
        thread_keys = source_ref_thread_keys(refs)
        context = TermQualityContext(
            ingress="subconscious",
            reviewed=str(item.get("concept_kind_status") or item.get("kind_status") or "")
            .casefold()
            == "reviewed",
            source_backed=True,
            hit_count=len(refs),
            thread_count=len(thread_keys),
        )
        if not term_quality.accepts(src, context) or not term_quality.accepts(dst, context):
            continue
        confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        edge_type = safe_edge_type(item.get("edge_type") or "related")
        key = (normalize_term(src), normalize_term(dst), edge_type)
        group = grouped.setdefault(
            key,
            {
                "src": normalize_term(src),
                "dst": normalize_term(dst),
                "edge_type": edge_type,
                "confidence": 0.0,
                "refs": [],
                "_ref_seen": set(),
                "thread_keys": [],
                "_thread_key_seen": set(),
                "statuses": [],
                "signals": [],
                "src_kind": item.get("src_concept_kind") or item.get("source_concept_kind"),
                "dst_kind": item.get("dst_concept_kind") or item.get("target_concept_kind"),
                "kind_status": item.get("concept_kind_status") or item.get("kind_status"),
            },
        )
        group["confidence"] = max(float(group["confidence"] or 0.0), confidence)
        ref_seen = group["_ref_seen"]
        for ref in refs:
            identity = source_ref_identity(ref)
            if identity in ref_seen:
                continue
            ref_seen.add(identity)
            group["refs"].append(ref)
        thread_key_seen = group["_thread_key_seen"]
        for thread_key in thread_keys:
            if thread_key in thread_key_seen:
                continue
            thread_key_seen.add(thread_key)
            group["thread_keys"].append(thread_key)
        group["statuses"].append(item.get("status") or "staging")
        group["signals"].append(
            item.get("lifecycle_signal")
            or item.get("lifecycle_status")
            or item.get("retirement_signal")
            or item.get("status")
            or "staging"
        )
        if not group.get("src_kind"):
            group["src_kind"] = item.get("src_concept_kind") or item.get("source_concept_kind")
        if not group.get("dst_kind"):
            group["dst_kind"] = item.get("dst_concept_kind") or item.get("target_concept_kind")
        if not group.get("kind_status"):
            group["kind_status"] = item.get("concept_kind_status") or item.get("kind_status")

    hub_decisions, hub_quality = assess_subconscious_hub_quality(grouped.values())
    inserted = 0
    for group in grouped.values():
        refs = [ref for ref in group.get("refs") or [] if isinstance(ref, dict)]
        thread_keys = [str(key) for key in group.get("thread_keys") or [] if key]
        source_thread_key = thread_keys[0] if thread_keys else refs[0].get("thread_key")
        status_signal = strongest_lifecycle_signal(
            list(group.get("statuses") or []) + list(group.get("signals") or [])
        )
        status, lifecycle_reason = lifecycle_decision(
            requested_status=status_signal,
            confidence=float(group.get("confidence") or 0.0),
            evidence_count=len(refs),
            thread_count=len(thread_keys),
            lifecycle_signal=status_signal,
            source_backed=bool(refs),
        )
        edge_status = status
        edge_lifecycle_reason = lifecycle_reason
        group_key = (
            normalize_term(str(group["src"])),
            normalize_term(str(group["dst"])),
            str(group["edge_type"]),
        )
        slice_key = _stable_slice_key(*group_key)
        if decision := hub_decisions.get(group_key):
            edge_status = decision.status
            edge_lifecycle_reason = decision.reason
        src_id = upsert_concept(
            con,
            str(group["src"]),
            status=status,
            lifecycle_reason=lifecycle_reason,
            hit_count=len(refs),
            thread_count=len(thread_keys),
            supplied_kind=group.get("src_kind"),
            supplied_kind_status=group.get("kind_status"),
            source_backed_kind=bool(refs),
            contribution_source_family="subconscious_edges",
            contribution_slice_key=slice_key,
        )
        dst_id = upsert_concept(
            con,
            str(group["dst"]),
            status=status,
            lifecycle_reason=lifecycle_reason,
            hit_count=len(refs),
            thread_count=len(thread_keys),
            supplied_kind=group.get("dst_kind"),
            supplied_kind_status=group.get("kind_status"),
            source_backed_kind=bool(refs),
            contribution_source_family="subconscious_edges",
            contribution_slice_key=slice_key,
        )
        if not src_id or not dst_id:
            continue
        upsert_edge(
            con,
            src_id,
            dst_id,
            edge_type=str(group["edge_type"]),
            confidence=float(group.get("confidence") or 0.0),
            status=edge_status,
            evidence_count=len(refs),
            lifecycle_reason=edge_lifecycle_reason,
            thread_count=len(thread_keys),
            source_thread_key=source_thread_key,
            contribution_source_family="subconscious_edges",
            contribution_slice_key=slice_key,
        )
        inserted += 1
        if group["edge_type"] in edge_policy.BIDIRECTIONAL_EDGE_TYPES:
            upsert_edge(
                con,
                dst_id,
                src_id,
                edge_type=str(group["edge_type"]),
                confidence=float(group.get("confidence") or 0.0),
                status=edge_status,
                evidence_count=len(refs),
                lifecycle_reason=edge_lifecycle_reason,
                thread_count=len(thread_keys),
                source_thread_key=source_thread_key,
                contribution_source_family="subconscious_edges",
                contribution_slice_key=slice_key,
            )
            inserted += 1
    return inserted, hub_quality


__all__ = ["collect_subconscious_edges", "iter_concept_graph_rows"]
