#!/usr/bin/env python3
"""Parallel derivation bundle and pre-flattening compatibility gate.

The bundle is a diagnostic envelope for existing macro/navigation derivations.
It checks source-basis alignment, dependency order, and cross-derivation tension
before downstream route/fanout surfaces flatten navigation signals.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, stable_json_join_id
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.source_shape import build_source_shape_descriptor

BUNDLE_KIND = "parallel_derivation_bundle"
SCHEMA_VERSION = 1
AUTHORITY_LEVEL = "navigation_only"
CLAIM_PERMISSION = "none"

COMPATIBLE = "compatible"
TENSION = "tension"
OBSTRUCTION = "obstruction"
INCOMPLETE = "incomplete"
STATUSES = {COMPATIBLE, TENSION, OBSTRUCTION, INCOMPLETE}

DEGRADE_TO = {
    COMPATIBLE: "reopenable_route",
    TENSION: "recheck_or_narrow",
    OBSTRUCTION: "source_reopen_review",
    INCOMPLETE: "diagnostic_only",
}


def _text(value: Any, limit: int = 120) -> str:
    return compact_text(str(value or ""), limit)


def _code(value: Any, *, fallback: str = "", limit: int = 80) -> str:
    text = _text(value, limit).casefold().replace(" ", "_").replace("-", "_")
    safe = "".join(ch for ch in text if ch.isalnum() or ch == "_").strip("_")
    return safe or fallback


def _codes(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[Any] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    for item in raw_items:
        code = _code(item)
        if code and code not in out:
            out.append(code)
        if len(out) >= limit:
            break
    return out


def _redact(value: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(value))


def _derivation_id(row: Mapping[str, Any], index: int) -> str:
    value = row.get("derivation_id") or row.get("id") or row.get("kind") or f"derivation_{index}"
    return _code(value, fallback=f"derivation_{index}", limit=100)


def _derivation_kind(row: Mapping[str, Any]) -> str:
    return _code(row.get("derivation_kind") or row.get("kind"), fallback="derivation", limit=80)


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("source_id") or ref.get("thread_key") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ref.get("turn_index") or ""),
        str(ref.get("line") or ""),
    )


def _refs_for_derivation(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = safe_source_refs(row.get("source_refs") or row.get("source_basis") or row.get("source_handles"))
    return refs[:12]


def normalize_derivations(derivations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(derivations):
        if not isinstance(raw, Mapping):
            continue
        derivation_id = _derivation_id(raw, index)
        if derivation_id in seen:
            derivation_id = f"{derivation_id}_{index}"
        seen.add(derivation_id)
        refs = _refs_for_derivation(raw)
        raw_shape = raw.get("shape")
        shape: Mapping[str, Any] = raw_shape if isinstance(raw_shape, Mapping) else {}
        row = {
            "derivation_id": derivation_id,
            "derivation_kind": _derivation_kind(raw),
            "derived_from_state_id": _text(raw.get("derived_from_state_id") or raw.get("state_id"), 120),
            "prerequisite_derivation_ids": _codes(raw.get("prerequisite_derivation_ids"), limit=12),
            "source_refs": refs,
            "source_ref_count": len(refs),
            "source_family": _code(raw.get("source_family") or raw.get("route_family"), fallback="unknown"),
            "source_epoch": _text(raw.get("source_epoch"), 120),
            "source_window": _redact(raw.get("source_window") or raw.get("source_coverage_time") or {}),
            "shape": {
                _code(key, fallback="field"): _text(value, 120)
                for key, value in shape.items()
                if _code(key, fallback="")
            },
            "status": _code(raw.get("status"), fallback="ready"),
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
            "fact_claim_allowed": False,
        }
        redacted = _redact(row)
        rows.append(redacted if isinstance(redacted, dict) else row)
    return rows


def source_basis_alignment(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    per_basis: list[dict[str, Any]] = []
    key_sets: list[set[tuple[str, str, str, str]]] = []
    for row in rows:
        refs = safe_source_refs(row.get("source_refs"))
        keys = {_ref_key(ref) for ref in refs if _ref_key(ref)[0] or _ref_key(ref)[1]}
        key_sets.append(keys)
        per_basis.append(
            {
                "derivation_id": row.get("derivation_id"),
                "source_refs": refs,
                "source_ref_count": len(refs),
                "source_family": row.get("source_family"),
                "source_epoch": row.get("source_epoch"),
                "source_window": row.get("source_window") or {},
            }
        )
    nonempty = [keys for keys in key_sets if keys]
    if not rows or not nonempty:
        alignment = "missing"
        shared: set[tuple[str, str, str, str]] = set()
        reason_codes = ["missing_source_basis"]
    else:
        shared = set.intersection(*nonempty)
        pairwise_shared: set[tuple[str, str, str, str]] = set()
        for index, keys in enumerate(nonempty):
            for other in nonempty[index + 1 :]:
                pairwise_shared.update(keys & other)
        union = set.union(*nonempty)
        if shared and len(nonempty) == len(rows):
            alignment = "shared"
            reason_codes = ["shared_source_basis"]
        elif shared or pairwise_shared:
            alignment = "partial_overlap"
            reason_codes = ["partial_source_basis_overlap"]
            shared = shared or pairwise_shared
        elif union:
            alignment = "no_overlap"
            reason_codes = ["no_shared_source_basis"]
        else:
            alignment = "missing"
            reason_codes = ["missing_source_basis"]
    refs_by_key = {
        _ref_key(ref): ref
        for row in rows
        for ref in safe_source_refs(row.get("source_refs"))
        if _ref_key(ref)[0] or _ref_key(ref)[1]
    }
    shared_refs = [refs_by_key[key] for key in sorted(shared)]
    return {
        "alignment": alignment,
        "shared_source_refs": shared_refs,
        "per_derivation_basis": per_basis,
        "reason_codes": reason_codes,
        "source_handles_only": True,
        "shared_vocabulary_is_not_source_support": True,
        "macro_coordinates_are_not_source_support": True,
    }


def dependency_dag(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [str(row.get("derivation_id") or "") for row in rows if row.get("derivation_id")]
    id_set = set(ids)
    prerequisites = {
        str(row.get("derivation_id")): _codes(row.get("prerequisite_derivation_ids"), limit=24)
        for row in rows
        if row.get("derivation_id")
    }
    missing = sorted(
        {
            prereq
            for prereqs in prerequisites.values()
            for prereq in prereqs
            if prereq not in id_set
        }
    )
    edges = [
        {"from": prereq, "to": derivation_id}
        for derivation_id, prereqs in prerequisites.items()
        for prereq in prereqs
        if prereq in id_set
    ]

    dependents: dict[str, list[str]] = defaultdict(list)
    incoming = {derivation_id: 0 for derivation_id in ids}
    for edge in edges:
        dependents[str(edge["from"])].append(str(edge["to"]))
        incoming[str(edge["to"])] += 1
    ready = deque([derivation_id for derivation_id in ids if incoming[derivation_id] == 0])
    topo: list[str] = []
    while ready:
        current = ready.popleft()
        topo.append(current)
        for target in sorted(dependents.get(current, [])):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    cycle = len(topo) != len(ids)
    reason_codes: list[str] = []
    if missing:
        reason_codes.append("missing_prerequisite_derivation")
    if cycle:
        reason_codes.append("cyclic_derivation_dependency")
    if topo and topo != ids:
        reason_codes.append("input_order_repaired_by_dependency_dag")
    if not reason_codes:
        reason_codes.append("dependency_dag_valid")
    return {
        "nodes": ids,
        "edges": edges,
        "topological_order": topo,
        "input_order": ids,
        "missing_prerequisites": missing,
        "cycle_detected": cycle,
        "reason_codes": reason_codes,
        "ordering_is_for_snapshot_fidelity_not_authority": True,
    }


def _shape(row: Mapping[str, Any]) -> Mapping[str, Any]:
    shape = row.get("shape")
    return shape if isinstance(shape, Mapping) else {}


def _has_shape_value(rows: Sequence[Mapping[str, Any]], kind: str, key: str, values: set[str]) -> bool:
    for row in rows:
        if row.get("derivation_kind") != kind:
            continue
        value = _code(_shape(row).get(key) or row.get(key))
        if value in values:
            return True
    return False


def _source_families_for(rows: Sequence[Mapping[str, Any]], kind: str, shape_key: str) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("derivation_kind") != kind:
            continue
        shape_value = _code(_shape(row).get(shape_key), fallback="")
        if shape_value:
            grouped[shape_value].add(str(row.get("source_family") or "unknown"))
    return grouped


def compatibility_diagnostics(
    rows: Sequence[Mapping[str, Any]],
    *,
    basis_alignment: Mapping[str, Any],
    dag: Mapping[str, Any],
    compute_compatibility: bool = True,
) -> dict[str, Any]:
    reasons: list[str]
    if not compute_compatibility:
        status = INCOMPLETE
        reasons = ["missing_parallel_compatibility_diagnostics"]
    else:
        blocking: list[str] = []
        tension: list[str] = []
        basis_state = str(basis_alignment.get("alignment") or "missing")
        if basis_state == "missing":
            blocking.append("missing_source_basis")
        elif basis_state == "no_overlap":
            blocking.append("no_shared_source_basis")
        elif basis_state == "partial_overlap":
            tension.append("partial_source_basis_overlap")
        for code in dag.get("reason_codes") or []:
            safe = _code(code)
            if safe in {"missing_prerequisite_derivation", "cyclic_derivation_dependency"}:
                blocking.append(safe)
            elif safe == "input_order_repaired_by_dependency_dag":
                tension.append(safe)

        if _has_shape_value(rows, "momentum", "direction", {"rising", "up", "increase"}) and _has_shape_value(
            rows,
            "shadow_route",
            "posture",
            {"collapsing", "obstructed", "blocked"},
        ):
            blocking.append("latent_route_conflict")
        if _has_shape_value(rows, "perturbation", "band", {"large", "wide"}) and _has_shape_value(
            rows,
            "three_powers",
            "active_axis_width",
            {"narrow", "single"},
        ):
            tension.append("fanout_tension")
        if _has_shape_value(rows, "three_powers", "heaven_direction", {"clear", "strong"}) and _has_shape_value(
            rows,
            "earth_evidence",
            "evidence",
            {"missing", "thin", "absent"},
        ):
            blocking.append("interlayer_obstruction")
        for families in _source_families_for(rows, "transform_orbit", "orbit_id").values():
            if len({family for family in families if family and family != "unknown"}) > 1:
                tension.append("same_structure_different_source_family")
        if _has_shape_value(rows, "stage_tracker", "movement", {"fork", "reversal"}) and (
            _has_shape_value(rows, "momentum", "direction", {"rising", "increase"})
            or _has_shape_value(rows, "perturbation", "band", {"large", "wide"})
        ):
            tension.append("stage_movement_conflict")

        reasons = []
        for code in [*blocking, *tension]:
            if code not in reasons:
                reasons.append(code)
        if blocking:
            status = OBSTRUCTION
        elif tension:
            status = TENSION
        else:
            status = COMPATIBLE
            reasons.append("parallel_derivations_compatible")

    severity = {
        COMPATIBLE: "ok",
        TENSION: "review",
        OBSTRUCTION: "block",
        INCOMPLETE: "incomplete",
    }[status]
    route_projection_allowed = status == COMPATIBLE
    return {
        "kind": "parallel_derivation_compatibility_diagnostic",
        "status": status,
        "severity": severity,
        "reason_codes": reasons,
        "degrade_to": DEGRADE_TO[status],
        "route_projection_allowed": route_projection_allowed,
        "avatar_projection_allowed": route_projection_allowed,
        "fact_claim_allowed": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "diagnostic_surface": "explain_deepen_or_campus_first",
    }


def _shape_dimensions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "derivation_id": row.get("derivation_id"),
            "derivation_kind": row.get("derivation_kind"),
            "shape": row.get("shape") or {},
            "source_family": row.get("source_family"),
            "source_ref_count": row.get("source_ref_count"),
        }
        for row in rows
    ]


def _all_source_refs(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        for ref in safe_source_refs(row.get("source_refs")):
            key = _ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    return refs


def build_parallel_derivation_bundle(
    derivations: Sequence[Mapping[str, Any]],
    *,
    bundle_id: str = "",
    source_snapshot: Mapping[str, Any] | None = None,
    created_at: str | None = None,
    compute_compatibility: bool = True,
) -> dict[str, Any]:
    rows = normalize_derivations(derivations)
    basis = source_basis_alignment(rows)
    dag = dependency_dag(rows)
    compatibility = compatibility_diagnostics(
        rows,
        basis_alignment=basis,
        dag=dag,
        compute_compatibility=compute_compatibility,
    )
    all_refs = _all_source_refs(rows)
    created = created_at or now_utc()
    safe_snapshot = source_snapshot if isinstance(source_snapshot, Mapping) else {}
    shape_id = stable_json_join_id(
        "parallel_shape",
        bundle_id,
        rows,
        basis,
        dag,
        sep="\0",
        ensure_ascii=False,
        length=20,
    )
    descriptor = build_source_shape_descriptor(
        producer="parallel_derivation_bundle",
        source_refs=all_refs,
        source_snapshot={
            "snapshot_id": safe_snapshot.get("snapshot_id") or bundle_id or shape_id,
            "source_ids": safe_snapshot.get("source_ids") or [ref.get("source_id") for ref in all_refs if ref.get("source_id")],
            "source_epoch": safe_snapshot.get("source_epoch"),
            "topic_epoch": safe_snapshot.get("topic_epoch"),
            "coverage_scope": basis.get("alignment"),
        },
        derivation_dag=dag,
        compatibility_diagnostics=compatibility,
        temporal={
            "source_coverage_time": safe_snapshot.get("source_coverage_time") or safe_snapshot.get("section_time_window"),
            "materialized_at": created,
            "built_at": created,
            "source_epoch": safe_snapshot.get("source_epoch"),
            "topic_epoch": safe_snapshot.get("topic_epoch"),
            "review_after": safe_snapshot.get("review_after"),
        },
        guard_inputs={
            "parallel_compatibility": compatibility["status"],
            "projection_allowed": compatibility["status"] == COMPATIBLE,
        },
        signals={"compatibility": {"status": compatibility["status"]}},
        source_shape_id=shape_id,
        created_at=created,
    )
    bundle = {
        "kind": BUNDLE_KIND,
        "schema_version": SCHEMA_VERSION,
        "bundle_id": _text(bundle_id, 120)
        or stable_json_join_id(
            "pdb",
            rows,
            safe_snapshot,
            sep="\0",
            ensure_ascii=False,
            length=20,
        ),
        "created_at": created,
        "derivations": rows,
        "source_basis": basis,
        "dependency_dag": dag,
        "shape_dimensions": _shape_dimensions(rows),
        "compatibility": compatibility,
        "source_shape_descriptor": descriptor,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_boundary": {
            "parallel_bundle_is_navigation_diagnostic": True,
            "source_handles_only": True,
            "source_reopen_required_before_claim": True,
            "shared_vocabulary_or_shape_is_not_source_support": True,
        },
    }
    redacted = _redact(bundle)
    return redacted if isinstance(redacted, dict) else bundle


def preflattening_gate_for_route_affordance(bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        return {
            "kind": "parallel_derivation_preflattening_gate",
            "status": INCOMPLETE,
            "flattening_allowed": False,
            "reason_codes": ["missing_parallel_derivation_bundle"],
            "degrade_to": DEGRADE_TO[INCOMPLETE],
            "required_next": "build_parallel_derivation_bundle_or_skip_macro_flattening",
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
            "fact_claim_allowed": False,
        }
    raw_compatibility = bundle.get("compatibility")
    compatibility: Mapping[str, Any] = raw_compatibility if isinstance(raw_compatibility, Mapping) else {}
    status = _code(compatibility.get("status"), fallback=INCOMPLETE)
    if status not in STATUSES:
        status = INCOMPLETE
    reason_codes = _codes(compatibility.get("reason_codes"), limit=8) or ["missing_parallel_compatibility_diagnostics"]
    if status == COMPATIBLE:
        flattening_allowed = True
        required_next = "ordinary_navigation_projection"
    elif status == TENSION:
        flattening_allowed = False
        required_next = "recheck_or_narrow_before_broad_fanout"
    else:
        flattening_allowed = False
        required_next = "source_reopen_or_review_before_route_use"
    return {
        "kind": "parallel_derivation_preflattening_gate",
        "status": status,
        "flattening_allowed": flattening_allowed,
        "reason_codes": reason_codes,
        "degrade_to": compatibility.get("degrade_to") or DEGRADE_TO[status],
        "required_next": required_next,
        "source_shape_id": ((bundle.get("source_shape_descriptor") or {}).get("source_shape_id"))
        if isinstance(bundle.get("source_shape_descriptor"), Mapping)
        else "",
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
    }


__all__ = [
    "BUNDLE_KIND",
    "COMPATIBLE",
    "INCOMPLETE",
    "OBSTRUCTION",
    "TENSION",
    "build_parallel_derivation_bundle",
    "compatibility_diagnostics",
    "dependency_dag",
    "preflattening_gate_for_route_affordance",
    "source_basis_alignment",
]
