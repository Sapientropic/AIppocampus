from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from aippocampus_runtime.macro.hexagram import HexagramRef, change_lines, resolve_hexagram
from aippocampus_runtime.macro.perturbation import (
    AUTHORITY_LEVEL,
    CLAIM_PERMISSION,
    build_perturbation_packet,
    compact_perturbation_label,
)

SCHEMA_VERSION = "0.1"
ACTION_GRAMMAR = "direction_only"
KIND = "macro_orientation_state"
DEFAULT_RECHECK_TRIGGERS = (
    "roadmap_shift",
    "benchmark_result",
    "repeated_route_failure",
)
ALLOWED_INPUT_SIGNAL_SCALES = frozenset({"journey", "continuity_domain", "project_event"})
PROMOTION_REASONS = frozenset(
    {
        "project_source_event",
        "domain_transition",
        "benchmark_result",
        "roadmap_shift",
        "repeated_route_failure",
        "explicit_review",
    }
)
MOMENTUM_BASIS_KEYS = (
    "support_delta",
    "counter_evidence_delta",
    "route_success_delta",
    "staleness_delta",
    "user_correction_delta",
)
FORBIDDEN_RAW_KEYS = frozenset(
    {
        "raw_text",
        "source_text",
        "text",
        "body",
        "content",
        "prompt",
        "local_path",
    }
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_momentum_block() -> dict[str, object]:
    return {
        "phase": None,
        "direction": None,
        "basis": {key: 0.0 for key in MOMENTUM_BASIS_KEYS},
        "authority_level": AUTHORITY_LEVEL,
        "status": "reserved_for_momentum_phase_slice",
    }


def _normalize_changing_lines(changing: Iterable[int]) -> tuple[int, ...]:
    positions = tuple(changing)
    if any(type(position) is not int for position in positions):
        raise ValueError("changing lines must be integers")
    if any(position < 1 or position > 6 for position in positions):
        raise ValueError("changing lines are 1-based, bottom-to-top, from 1 to 6")
    if len(set(positions)) != len(positions):
        raise ValueError("changing lines must not repeat")
    return tuple(sorted(positions))


def _hexagram_projection(value: HexagramRef) -> dict[str, object]:
    item = resolve_hexagram(value)
    return {
        "name": item.name,
        "number": item.number,
        "bits_bottom_to_top": item.bitstring_bottom_to_top,
        "upper_trigram": item.upper_trigram,
        "lower_trigram": item.lower_trigram,
    }


def _normalize_input_signal_scales(scales: Iterable[str]) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(scales))
    if not values:
        raise ValueError("macro orientation state must name at least one input signal scale")
    unknown = sorted(set(values) - ALLOWED_INPUT_SIGNAL_SCALES)
    if unknown:
        raise ValueError(f"unsupported macro orientation input signal scales: {unknown!r}")
    return values


def build_macro_orientation_state(
    *,
    project: str,
    hexagram: HexagramRef,
    changing_lines: Iterable[int] = (),
    source_refs: Iterable[Mapping[str, object]] = (),
    input_signal_scales: Iterable[str] = ("project_event",),
    promotion_reason: str | None = None,
    updated_at: str | None = None,
    recheck_on: Iterable[str] = DEFAULT_RECHECK_TRIGGERS,
    stale_after_days: int = 30,
    active_layer: str = "人",
    momentum: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not project.strip():
        raise ValueError("project must be a non-empty string")
    stamp = updated_at or utc_now_iso()
    positions = _normalize_changing_lines(changing_lines)
    current = resolve_hexagram(hexagram)
    toward = change_lines(current, positions) if positions else current
    scales = _normalize_input_signal_scales(input_signal_scales)
    perturbation = build_perturbation_packet(
        current,
        toward,
        signal_scale="project_event" if "project_event" in scales else "unknown",
        promoted_to_project=promotion_reason is not None,
    )

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "state_id": f"macro:{project}:{stamp}:{current.number}:{toward.number}",
        "updated_at": stamp,
        "scope": {"kind": "project", "project": project},
        "input_signal_scales": list(scales),
        "write_scale": "project",
        "promotion": {
            "required_for_non_project_signals": True,
            "reason": promotion_reason,
            "allowed_reasons": sorted(PROMOTION_REASONS),
        },
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "hexagram": _hexagram_projection(current),
        "changing_lines": list(positions),
        "movement": {
            "toward": toward.name,
            "toward_number": toward.number,
            "mode": "structural_transition" if positions else "standing_state",
        },
        "perturbation": compact_perturbation_label(perturbation),
        "relation_position": {
            "situation_role": "世",
            "current_agent_default_role": "应",
            "active_layer": active_layer,
        },
        "momentum": dict(momentum) if momentum is not None else default_momentum_block(),
        "source_refs": [dict(ref) for ref in source_refs],
        "recheck_on": list(recheck_on),
        "stale_after_days": stale_after_days,
        "derivation_trace": [
            "hexagram_resolved_by_deterministic_runtime",
            "movement_derived_from_bottom_to_top_changing_lines",
            "authority_forced_to_navigation_only",
        ],
        "source_boundary": {
            "navigation_only_not_fact": True,
            "no_raw_private_text": True,
            "macro_state_is_not_current_instruction": True,
            "scale_boundary": "write_scale_project_only",
        },
    }


def _has_forbidden_raw_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) in FORBIDDEN_RAW_KEYS:
                return True
            if _has_forbidden_raw_key(nested):
                return True
    if isinstance(value, list | tuple):
        return any(_has_forbidden_raw_key(item) for item in value)
    return False


def _parse_updated_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _source_status(entry: Mapping[str, object]) -> str:
    refs = entry.get("source_refs")
    if not isinstance(refs, list) or not refs:
        return "missing_source"
    for ref in refs:
        if not isinstance(ref, Mapping):
            return "invalid_source_ref"
        if not any(key in ref for key in ("source_id", "ref_id", "url")):
            return "invalid_source_ref"
    return "source_refs_present"


def validate_macro_orientation_state(entry: Mapping[str, object]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if entry.get("kind") != KIND:
        errors.append("kind_must_be_macro_orientation_state")
    if entry.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_schema_version")
    scope = entry.get("scope")
    if not isinstance(scope, Mapping) or scope.get("kind") != "project" or not scope.get("project"):
        errors.append("scope_must_be_project")
    if entry.get("write_scale") != "project":
        errors.append("write_scale_must_be_project")
    if entry.get("authority_level") != AUTHORITY_LEVEL:
        errors.append("authority_must_be_navigation_only")
    if entry.get("action_grammar") != ACTION_GRAMMAR:
        errors.append("action_grammar_must_be_direction_only")
    if entry.get("claim_permission") != CLAIM_PERMISSION:
        errors.append("claim_permission_must_require_reopen")
    if _parse_updated_at(entry.get("updated_at")) is None:
        errors.append("updated_at_must_be_iso_datetime")
    if _has_forbidden_raw_key(entry):
        errors.append("raw_private_text_or_local_path_field_forbidden")

    scales_raw = entry.get("input_signal_scales")
    scales = tuple(scales_raw) if isinstance(scales_raw, list) else ()
    if not scales or set(scales) - ALLOWED_INPUT_SIGNAL_SCALES:
        errors.append("input_signal_scales_invalid")
    promotion = entry.get("promotion")
    promotion_reason = promotion.get("reason") if isinstance(promotion, Mapping) else None
    if promotion_reason is not None and promotion_reason not in PROMOTION_REASONS:
        errors.append("promotion_reason_invalid")
    non_project_scales = set(scales) - {"project_event"}
    if non_project_scales and "project_event" not in scales and promotion_reason not in PROMOTION_REASONS:
        errors.append("non_project_signal_requires_promotion")

    try:
        hexagram = entry.get("hexagram")
        if not isinstance(hexagram, Mapping):
            raise ValueError("hexagram block missing")
        resolved = resolve_hexagram(str(hexagram.get("name")))
        if hexagram.get("bits_bottom_to_top") != resolved.bitstring_bottom_to_top:
            errors.append("hexagram_bit_convention_mismatch")
    except ValueError:
        errors.append("hexagram_must_resolve")

    changing = entry.get("changing_lines")
    if not isinstance(changing, list):
        errors.append("changing_lines_must_be_list")
    else:
        try:
            _normalize_changing_lines(tuple(changing))
        except (TypeError, ValueError):
            errors.append("changing_lines_invalid")

    source_status = _source_status(entry)
    if source_status == "missing_source":
        warnings.append("missing_source_refs_degrade_to_diagnostic")
    elif source_status == "invalid_source_ref":
        errors.append("source_refs_invalid")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "source_status": source_status,
    }


def append_macro_orientation_state(path: Path, entry: Mapping[str, object]) -> None:
    validation = validate_macro_orientation_state(entry)
    if not validation["ok"]:
        raise ValueError(f"invalid macro orientation state: {validation['errors']!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(entry), ensure_ascii=False, sort_keys=True) + "\n")


def load_macro_orientation_states(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def explain_macro_orientation_state(entry: Mapping[str, object]) -> dict[str, object]:
    return {
        "kind": "macro_orientation_state_diagnostics",
        "state_id": entry.get("state_id"),
        "source_refs": entry.get("source_refs", []),
        "derivation_trace": entry.get("derivation_trace", []),
        "validation": validate_macro_orientation_state(entry),
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "source_boundary": entry.get("source_boundary", {}),
    }


def _entry_project(entry: Mapping[str, object]) -> str | None:
    scope = entry.get("scope")
    if not isinstance(scope, Mapping):
        return None
    if scope.get("kind") != "project":
        return None
    project = scope.get("project")
    return project if isinstance(project, str) else None


def _entry_stale_after_days(entry: Mapping[str, object]) -> int:
    value = entry.get("stale_after_days", 30)
    return value if type(value) is int else 30


def latest_project_macro_orientation(
    entries: Iterable[Mapping[str, object]],
    *,
    project: str,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    project_entries = [entry for entry in entries if _entry_project(entry) == project]
    if not project_entries:
        return {
            "kind": "macro_orientation_latest_projection",
            "project": project,
            "status": "missing",
            "usable_as_current_navigation_pointer": False,
            "usable_as_current_instruction": False,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
        }

    dated = [(entry, _parse_updated_at(entry.get("updated_at"))) for entry in project_entries]
    dated = [(entry, stamp) for entry, stamp in dated if stamp is not None]
    if not dated:
        return _diagnostic_projection(project, "invalid", project_entries[-1])
    latest_stamp = max(stamp for _, stamp in dated if stamp is not None)
    latest_entries = [entry for entry, stamp in dated if stamp == latest_stamp]
    unique_shapes = {
        json.dumps(entry.get("hexagram"), ensure_ascii=False, sort_keys=True)
        + json.dumps(entry.get("movement"), ensure_ascii=False, sort_keys=True)
        for entry in latest_entries
    }
    if len(unique_shapes) > 1:
        return _diagnostic_projection(project, "conflicting", latest_entries[0], entries=latest_entries)

    latest = latest_entries[0]
    validation = validate_macro_orientation_state(latest)
    if not validation["ok"]:
        return _diagnostic_projection(project, "invalid", latest)
    if validation["source_status"] != "source_refs_present":
        return _diagnostic_projection(project, "missing_source", latest)
    stale_after_days = _entry_stale_after_days(latest)
    if (now - latest_stamp).days > stale_after_days:
        return _diagnostic_projection(project, "stale", latest)

    return {
        "kind": "macro_orientation_latest_projection",
        "project": project,
        "status": "current",
        "state": dict(latest),
        "usable_as_current_navigation_pointer": True,
        "usable_as_current_instruction": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "diagnostics": explain_macro_orientation_state(latest),
    }


def _diagnostic_projection(
    project: str,
    status: str,
    entry: Mapping[str, object],
    *,
    entries: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "kind": "macro_orientation_latest_projection",
        "project": project,
        "status": status,
        "state": dict(entry),
        "conflicting_entries": [dict(row) for row in entries] if entries else [],
        "usable_as_current_navigation_pointer": False,
        "usable_as_current_instruction": False,
        "diagnostic_only": True,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "diagnostics": explain_macro_orientation_state(entry),
    }


__all__ = [
    "ACTION_GRAMMAR",
    "ALLOWED_INPUT_SIGNAL_SCALES",
    "DEFAULT_RECHECK_TRIGGERS",
    "KIND",
    "MOMENTUM_BASIS_KEYS",
    "PROMOTION_REASONS",
    "SCHEMA_VERSION",
    "append_macro_orientation_state",
    "build_macro_orientation_state",
    "default_momentum_block",
    "explain_macro_orientation_state",
    "latest_project_macro_orientation",
    "load_macro_orientation_states",
    "utc_now_iso",
    "validate_macro_orientation_state",
]
