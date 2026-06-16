"""Source-backed total Macro/Yi hexagram encoder.

This module composes partial deterministic signals into a six-line state only
when every line has source-backed or explicitly reviewed provenance. It is
navigation metadata, never a source of claims or symbolic advice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.macro.hexagram import hexagram_from_lines
from aippocampus_runtime.macro.three_powers import normalize_layer

SCHEMA_VERSION = 1
KIND = "aippocampus_macro_total_hexagram_encoding"
AUTHORITY = "navigation_only"
CLAIM_PERMISSION = "no_claim_before_reopen"


def _safe_refs(value: Any, *, limit: int = 6) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        compact = {
            str(key): str(item.get(key) or "")[:160]
            for key in ("source_id", "message_id", "ref_id", "handle", "url")
            if item.get(key) is not None
        }
        if compact:
            refs.append(compact)
        if len(refs) >= limit:
            break
    return refs


def _private_scope(value: Mapping[str, Any]) -> bool:
    scope = str(
        value.get("privacy_scope")
        or value.get("privacy_partition")
        or value.get("scope")
        or "public"
    ).casefold()
    return "private" in scope or "local-only" in scope or "local_only" in scope


def _line_index(value: Any) -> int | None:
    if type(value) is int and 1 <= value <= 6:
        return value
    return None


def _line_value(value: Any) -> int | None:
    if type(value) is int and value in (0, 1):
        return value
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return int(value.strip())
    return None


def _empty_line(line: int) -> dict[str, Any]:
    return {
        "line": line,
        "state": "unknown",
        "value": None,
        "authority": "unknown",
        "source_refs": [],
        "reason_codes": ["line_signal_missing"],
    }


def _normalize_changing_lines(signals: Sequence[Mapping[str, Any]] | None) -> list[int]:
    result: list[int] = []
    for row in signals or []:
        line = _line_index(row.get("line"))
        if line is not None and line not in result and not _private_scope(row):
            result.append(line)
    return sorted(result)


def _active_layer(signal: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    if not isinstance(signal, Mapping):
        return "human", ["macro_active_layer_absent_default_human_for_router_only"]
    try:
        return normalize_layer(signal.get("active_layer") or signal.get("layer") or "human"), [
            "macro_active_layer_source_backed"
        ]
    except ValueError:
        return "human", ["macro_active_layer_invalid_default_human_for_router_only"]


def _momentum_block(signal: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(signal, Mapping):
        return {
            "phase": "hibernating",
            "phase_hint": "hibernating",
            "authority_level": AUTHORITY,
            "status": "momentum_absent",
        }
    phase = str(signal.get("phase") or signal.get("phase_hint") or "hibernating")
    return {
        "phase": phase,
        "phase_hint": phase,
        "basis": signal.get("basis") if isinstance(signal.get("basis"), Mapping) else {},
        "authority_level": AUTHORITY,
        "status": "source_backed_compact_trend_hint",
    }


def _state_hint(
    *,
    project: str,
    lines: tuple[int, int, int, int, int, int],
    changing_lines: list[int],
    active_layer: str,
    momentum: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, str]],
    status: str,
) -> dict[str, Any]:
    hexagram = hexagram_from_lines(lines)
    hexagram_projection = hexagram.to_public_dict()
    hexagram_projection["bits_bottom_to_top"] = hexagram_projection["bitstring_bottom_to_top"]
    return {
        "kind": "macro_orientation_state",
        "schema_version": 1,
        "scope": {"kind": "project", "project": project},
        "write_scale": "project",
        "authority_level": AUTHORITY,
        "action_grammar": "direction_only",
        "claim_permission": CLAIM_PERMISSION,
        "hexagram": hexagram_projection,
        "changing_lines": changing_lines,
        "movement": {
            "toward": hexagram.name,
            "toward_number": hexagram.number,
            "mode": "total_encoder_navigation_state",
        },
        "perturbation": {
            "changed_line_count": len(changing_lines),
            "route_policy": "broad_route_fanout" if len(changing_lines) >= 3 else "bounded_route_fanout",
        },
        "relation_position": {
            "situation_role": "世",
            "current_agent_default_role": "应",
            "active_layer": active_layer,
        },
        "momentum": dict(momentum),
        "source_refs": [dict(ref) for ref in source_refs[:6]],
        "recheck_on": ["macro_momentum_recheck"] if str(momentum.get("phase_hint")) in {"rising", "turning", "declining"} else [],
        "derivation_trace": [
            f"macro_total_encoder_status:{status}",
            "macro_total_encoder_navigation_only",
            "source_reopen_required_before_claim",
        ],
    }


def build_total_hexagram_encoding(
    *,
    project: str,
    line_signals: Sequence[Mapping[str, Any]] = (),
    changing_line_signals: Sequence[Mapping[str, Any]] | None = None,
    active_layer_signal: Mapping[str, Any] | None = None,
    momentum_signal: Mapping[str, Any] | None = None,
    explicit_reviewed_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    line_slots = {line: _empty_line(line) for line in range(1, 7)}
    reason_codes: list[str] = ["macro_total_encoder_navigation_only"]
    blocked = False
    ambiguous = False
    automatic_derivation = explicit_reviewed_state is None

    if explicit_reviewed_state is not None:
        raw_lines = explicit_reviewed_state.get("lines_bottom_to_top") or explicit_reviewed_state.get("lines")
        values = tuple(_line_value(item) for item in raw_lines) if isinstance(raw_lines, Sequence) else ()
        refs = _safe_refs(explicit_reviewed_state.get("source_refs"))
        if len(values) == 6 and all(value in (0, 1) for value in values) and refs:
            for line, value in enumerate(values, 1):
                line_slots[line] = {
                    "line": line,
                    "state": "known",
                    "value": value,
                    "authority": "explicit_reviewed",
                    "source_refs": refs[:2],
                    "reason_codes": ["explicit_reviewed_state"],
                }
        else:
            reason_codes.append("explicit_reviewed_state_incomplete")

    if explicit_reviewed_state is None:
        observed: dict[int, list[dict[str, Any]]] = {line: [] for line in range(1, 7)}
        for signal in line_signals:
            line = _line_index(signal.get("line"))
            value = _line_value(signal.get("value"))
            if line is None or value is None:
                continue
            if _private_scope(signal):
                blocked = True
                observed[line].append(
                    {
                        "value": value,
                        "authority": "blocked",
                        "source_refs": [],
                        "reason_codes": ["line_signal_private_or_local_blocked"],
                    }
                )
                continue
            refs = _safe_refs(signal.get("source_refs"))
            observed[line].append(
                {
                    "value": value,
                    "authority": "source_backed" if refs else "unknown",
                    "source_refs": refs,
                    "reason_codes": ["line_signal_source_backed"] if refs else ["line_signal_missing_source_ref"],
                }
            )
        for line, rows in observed.items():
            if not rows:
                continue
            values = {row["value"] for row in rows}
            if len(values) > 1:
                ambiguous = True
                line_slots[line] = {
                    "line": line,
                    "state": "ambiguous",
                    "value": None,
                    "authority": "cannot_verify",
                    "source_refs": [ref for row in rows for ref in row["source_refs"]][:3],
                    "reason_codes": ["conflicting_line_signals"],
                }
                continue
            row = rows[-1]
            line_slots[line] = {
                "line": line,
                "state": "known" if row["authority"] == "source_backed" else "unknown",
                "value": row["value"] if row["authority"] == "source_backed" else None,
                "authority": row["authority"],
                "source_refs": row["source_refs"],
                "reason_codes": row["reason_codes"],
            }

    known_values = [line_slots[line]["value"] for line in range(1, 7)]
    complete = all(value in (0, 1) for value in known_values)
    if blocked:
        status = "blocked"
        reason_codes.append("macro_total_input_blocked_private_or_local")
    elif ambiguous:
        status = "ambiguous"
        reason_codes.append("macro_total_line_signal_ambiguous")
    elif complete and explicit_reviewed_state is not None:
        status = "explicit_reviewed"
        reason_codes.append("macro_state_explicit_reviewed")
    elif complete:
        status = "derived_complete"
        reason_codes.append("macro_state_derived_complete")
    elif any(value in (0, 1) for value in known_values):
        status = "derived_partial"
        reason_codes.append("macro_state_derived_partial")
    else:
        status = "insufficient_source"
        reason_codes.append("macro_state_insufficient_source")

    active_layer, layer_codes = _active_layer(active_layer_signal)
    momentum = _momentum_block(momentum_signal)
    changing_lines = _normalize_changing_lines(changing_line_signals)
    source_refs = [ref for line in range(1, 7) for ref in line_slots[line]["source_refs"]]
    result: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "status": status,
        "authority": AUTHORITY,
        "claim_permission": CLAIM_PERMISSION,
        "automatic_derivation": automatic_derivation,
        "explicit_reviewed_input": explicit_reviewed_state is not None,
        "line_provenance": [line_slots[line] for line in range(1, 7)],
        "changing_lines": changing_lines,
        "active_layer": active_layer,
        "momentum_phase": momentum.get("phase_hint"),
        "source_refs": source_refs[:6],
        "usable_for_recall_fanout": status in {"derived_complete", "explicit_reviewed"},
        "usable_for_recheck_timing": status in {"derived_complete", "explicit_reviewed"},
        "usable_for_explain_only_diagnostics": status in {"derived_partial", "ambiguous", "insufficient_source", "blocked"},
        "reason_codes": [*reason_codes, *layer_codes],
        "public_projection_boundary": {
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "symbolic_advice_included": False,
        },
    }
    if complete:
        lines_tuple = tuple(int(value) for value in known_values)  # type: ignore[arg-type]
        hexagram = hexagram_from_lines(lines_tuple)
        hexagram_projection = hexagram.to_public_dict()
        hexagram_projection["bits_bottom_to_top"] = hexagram_projection["bitstring_bottom_to_top"]
        result["hexagram"] = hexagram_projection
        result["macro_state_hint"] = _state_hint(
            project=project,
            lines=lines_tuple,  # type: ignore[arg-type]
            changing_lines=changing_lines,
            active_layer=active_layer,
            momentum=momentum,
            source_refs=source_refs,
            status=status,
        )
    else:
        result["hexagram"] = {"status": "incomplete", "bits_bottom_to_top": "incomplete"}
    return result
