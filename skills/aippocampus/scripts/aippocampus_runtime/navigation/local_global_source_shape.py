"""Source-shape producer for local/global compatibility diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import now_utc, stable_json_join_id
from aippocampus_runtime.navigation.local_global_compatibility import (
    BLOCKED_BOUNDARY,
    GLUED_ROUTE,
    evaluate_local_global_compatibility,
)
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.source_shape import build_source_shape_descriptor


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items: Sequence[Any] = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    for item in raw_items:
        text = _text(item)
        if (
            text
            and len(text) <= 96
            and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
            and all(char.isalnum() or char in "-_.:#" for char in text)
            and text not in out
        ):
            out.append(text)
    return out


def _source_refs_from_sections(sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for section in sections:
        refs.extend(safe_source_refs(section.get("source_refs")))
        for source_id in _strings(
            section.get("source_ids")
            or section.get("source_ref_ids")
            or section.get("source_anchors")
            or section.get("source_handles")
        ):
            refs.append({"source_id": source_id})
    return safe_source_refs(refs)


def _first_mapping(sections: Sequence[Mapping[str, Any]], *keys: str) -> dict[str, Any]:
    for section in sections:
        for key in keys:
            value = section.get(key)
            if isinstance(value, Mapping) and value:
                return dict(value)
    return {}


def _source_ids(refs: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        source_id = _text(ref.get("source_id") or ref.get("thread_key"))
        if source_id and source_id not in out:
            out.append(source_id)
    return out


def _section_ids(compatibility: Mapping[str, Any]) -> list[str]:
    contracts = compatibility.get("section_contracts")
    if not isinstance(contracts, Sequence) or isinstance(contracts, (str, bytes, bytearray)):
        return []
    ids: list[str] = []
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        section_id = _text(contract.get("section_id"))
        if section_id and section_id not in ids:
            ids.append(section_id)
    return ids


def build_local_global_source_shape_descriptor(
    sections: Sequence[Mapping[str, Any]],
    *,
    producer: str = "local_global_sections",
    case_id: str = "local_global_source_shape",
    source_shape_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate local/global glue and feed the compact result into source-shape."""

    rows = [section for section in sections if isinstance(section, Mapping)]
    compatibility = evaluate_local_global_compatibility(rows, case_id=case_id)
    refs = _source_refs_from_sections(rows)
    section_ids = _section_ids(compatibility)
    created = created_at or now_utc()
    result = str(compatibility.get("result") or "")
    reason_codes = [str(code) for code in compatibility.get("reason_codes") or []]
    temporal: dict[str, Any] = {
        "source_coverage_time": _first_mapping(
            rows,
            "source_coverage_time",
            "section_time_window",
        ),
        "materialized_at": created,
        "built_at": created,
        "topic_epoch": rows[0].get("topic_epoch") if rows else "",
    }
    shape_id = source_shape_id or stable_json_join_id(
        "local_global_shape",
        producer,
        rows,
        compatibility,
        sep="\0",
        ensure_ascii=False,
        length=20,
    )
    return build_source_shape_descriptor(
        producer=producer,
        source_refs=refs,
        source_snapshot={
            "snapshot_id": shape_id,
            "source_ids": _source_ids(refs),
            "section_ids": section_ids,
            "topic_epoch": rows[0].get("topic_epoch") if rows else "",
            "coverage_scope": (compatibility.get("overlap_basis") or {}).get("common_scope_id"),
        },
        derivation_dag={
            "producer": producer,
            "nodes": section_ids,
            "edges": [],
        },
        compatibility_diagnostics=compatibility,
        temporal=temporal,
        guard_inputs={
            "parallel_compatibility": "complete",
            "projection_allowed": result == GLUED_ROUTE,
            "privacy_state": "blocked" if result == BLOCKED_BOUNDARY else "allowed",
            "freshness": "stale" if "stale_or_released_section_blocks_current_glue" in reason_codes else "current",
        },
        signals={"compatibility": {"status": result}},
        source_shape_id=shape_id,
        created_at=created,
    )


__all__ = ["build_local_global_source_shape_descriptor"]
