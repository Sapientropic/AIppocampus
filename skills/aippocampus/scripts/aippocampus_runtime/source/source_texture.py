"""Build source-texture rows from clean-source and safe process sidecars.

Source texture is a rebuildable interpretation input. It gives Dream, Journey,
and correction code enough process shape to choose where to look next, while
keeping source truth in clean-source messages, route notes, and event refs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import stable_text_id

SOURCE_TEXTURE_SCHEMA_VERSION = 1
SOURCE_TEXTURE_KIND = "aippocampus_source_texture"
SOURCE_TEXTURE_BOUNDARY = "texture_signal_not_source_fact"
SOURCE_TEXTURE_POLICY = {
    "version": "aippocampus-source-texture-v1",
    "default_file": "source-texture.jsonl",
    "purpose": "typed process texture for Dream, Journey, and correction routing",
    "boundary": "source texture rows are rebuildable interpretation inputs, not source truth.",
    "truth_boundary": SOURCE_TEXTURE_BOUNDARY,
    "output_authority": "interpretation_input_only",
    "source_reopen_required_before_claim": True,
    "clean_source_mutation_allowed": False,
    "external_model_calls": False,
    "raw_text_serialized": False,
}

SELF_CORRECTION_CUES = (
    ("visible_user_reformulation", ("不是这个意思", "我的意思是", "我是说", "i mean", "what i mean", "not that")),
    ("visible_user_correction", ("不对", "更正", "纠正", "actually", "correction", "let me rephrase")),
)
FRONTIER_CUES = (
    (
        "deferred_frontier",
        ("先留", "以后再", "回头再", "leave this for later", "later", "defer", "park this"),
    ),
    (
        "visible_uncertainty",
        ("不确定", "没想清楚", "不清楚", "待确认", "未解决", "not sure", "unclear", "open question", "unresolved"),
    ),
)
AFFECT_CUES = (
    ("visible_stuckness", ("卡住", "stuck", "blocked")),
    ("visible_frustration", ("烦", "挫败", "崩", "frustrated", "annoyed")),
    ("visible_relief", ("松一口气", "放心", "relieved", "relief")),
    ("visible_excitement", ("兴奋", "激动", "excited", "exciting")),
    ("visible_pressure", ("压力", "赶", "压迫", "pressure", "under pressure")),
)
ABANDONED_DIRECTION_CUES = (
    (
        "visible_abandoned_direction",
        ("先不要", "先不", "不要走", "不走", "放弃", "drop", "abandon", "skip for now"),
    ),
    ("visible_deferred_direction", ("暂缓", "搁置", "defer this route", "park this route")),
)
SAFE_EVENT_REF_FIELDS = (
    "event_id",
    "source_id",
    "source_ref",
    "turn_index",
    "source_line",
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
)
SAFE_SOURCE_REF_FIELDS = (
    "source_id",
    "source_ref",
    "message_id",
    "turn_id",
    "turn_index",
    "source_line",
    "raw_start_line",
    "raw_end_line",
    "clean_ordinal",
)


def _count_jsonl_rows(path: Path, default: int = 0) -> int:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return default


def _lowered(value: Any) -> str:
    return str(value or "").casefold()


def _matches(text: str, cue: str) -> bool:
    needle = cue.casefold()
    if re.match(r"^[a-z0-9_ -]+$", needle):
        return re.search(rf"(?<![a-z0-9_+-]){re.escape(needle)}(?![a-z0-9_+-])", text) is not None
    return needle in text


def _first_match(text: str, cue_groups: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for detail, cues in cue_groups:
        if any(_matches(text, cue) for cue in cues):
            return detail
    return None


def _clean_source_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {}
    for key in SAFE_SOURCE_REF_FIELDS:
        value = row.get(key)
        if value not in (None, "", []):
            ref["line" if key == "source_line" else key] = value
    if not ref.get("message_id"):
        message_id = row.get("id")
        if message_id:
            ref["message_id"] = message_id
    return ref


def _clean_event_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    ref = {
        ("line" if key == "source_line" else key): row.get(key)
        for key in SAFE_EVENT_REF_FIELDS
        if row.get(key) not in (None, "", [])
    }
    if "event_id" not in ref and row.get("id"):
        ref["event_id"] = row.get("id")
    return ref


def _dedupe_refs(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        cleaned = {str(key): value for key, value in dict(row).items() if value not in (None, "", [])}
        marker = tuple(sorted((key, str(value)) for key, value in cleaned.items()))
        if not cleaned or marker in seen:
            continue
        seen.add(marker)
        out.append(cleaned)
    return out


def _fingerprints(row: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in (
        "content_sha256",
        "text_sha1",
        "semantic_key",
        "input_sha256",
        "observation_sha256",
        "route_id_hash",
    ):
        value = row.get(key)
        if value not in (None, "", []):
            values[key] = value
    path_fingerprints = row.get("path_fingerprints")
    if isinstance(path_fingerprints, list) and path_fingerprints:
        values["path_fingerprints"] = [str(item) for item in path_fingerprints[:4]]
    return values


def _base_row(
    *,
    signal_kind: str,
    signal_detail: str,
    origin: str,
    source_refs: list[dict[str, Any]],
    event_refs: list[dict[str, Any]] | None = None,
    source_fingerprints: dict[str, Any] | None = None,
    role_scope: str = "source_visible",
    signal_labels: list[str] | None = None,
    freshness: str = "current",
) -> dict[str, Any]:
    event_refs = event_refs or []
    clean_source_refs = _dedupe_refs(source_refs)[:4]
    clean_event_refs = _dedupe_refs(event_refs)[:4]
    primary_ref = clean_source_refs[0] if clean_source_refs else {}
    primary_event_ref = clean_event_refs[0] if clean_event_refs else {}
    row: dict[str, Any] = {
        "kind": SOURCE_TEXTURE_KIND,
        "schema_version": SOURCE_TEXTURE_SCHEMA_VERSION,
        "texture_id": stable_text_id(
            signal_kind[:12], signal_kind, signal_detail, clean_source_refs, clean_event_refs
        ),
        "surface_kind": f"source_texture:{signal_kind}",
        "origin": origin,
        "texture_kind": signal_kind,
        "signal_kind": signal_kind,
        "signal_detail": signal_detail,
        "signal_labels": list(dict.fromkeys(signal_labels or [signal_detail])),
        "source_id": primary_ref.get("source_id") or primary_event_ref.get("source_id"),
        "turn_id": primary_ref.get("turn_id") or primary_event_ref.get("turn_id"),
        "turn_index": primary_ref.get("turn_index") or primary_event_ref.get("turn_index"),
        "message_id": primary_ref.get("message_id"),
        "event_id": primary_event_ref.get("event_id"),
        "role_scope": role_scope,
        "freshness": freshness,
        "privacy_profile": "raw-private",
        "truth_boundary": SOURCE_TEXTURE_BOUNDARY,
        "output_authority": "interpretation_input_only",
        "navigation_only": True,
        "source_reopen_required_before_claim": True,
        "consumer_boundary": "Dream/Journey/correction may use this row as routing texture only.",
        "source_refs": clean_source_refs,
        "event_refs": clean_event_refs,
        "source_fingerprints": source_fingerprints or {},
    }
    row["source_ref_count"] = len(clean_source_refs)
    row["event_ref_count"] = len(clean_event_refs)
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _message_rows(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message in messages:
        text = _lowered(message.get("text"))
        if not text:
            continue
        role = str(message.get("role") or "").casefold() or "unknown"
        source_ref = _clean_source_ref(message)
        if not source_ref:
            continue
        common: dict[str, Any] = {
            "source_refs": [source_ref],
            "source_fingerprints": _fingerprints(message),
            "role_scope": f"visible_{role}",
        }
        if role == "user":
            detail = _first_match(text, SELF_CORRECTION_CUES)
            if detail:
                rows.append(
                    _base_row(
                        signal_kind="self_correction_signal",
                        signal_detail=detail,
                        origin="clean_source_message",
                        signal_labels=["visible_correction", detail],
                        **common,
                    )
                )
            affect_detail = _first_match(text, AFFECT_CUES)
            if affect_detail:
                rows.append(
                    _base_row(
                        signal_kind="affect_marker",
                        signal_detail=affect_detail,
                        origin="clean_source_message",
                        signal_labels=["visible_affect", affect_detail],
                        **common,
                    )
                )
        frontier_detail = _first_match(text, FRONTIER_CUES)
        if frontier_detail:
            rows.append(
                _base_row(
                    signal_kind="uncertainty_or_frontier_signal",
                    signal_detail=frontier_detail,
                    origin="clean_source_message",
                    signal_labels=["visible_frontier", frontier_detail],
                    **common,
                )
            )
        abandoned_detail = _first_match(text, ABANDONED_DIRECTION_CUES)
        if abandoned_detail:
            rows.append(
                _base_row(
                    signal_kind="abandoned_direction",
                    signal_detail=abandoned_detail,
                    origin="clean_source_message",
                    signal_labels=["visible_route_boundary", abandoned_detail],
                    **common,
                )
            )
    return rows


def _event_rows(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        status = str(event.get("status") or "").casefold()
        hard_kind = str(event.get("hard_event_kind") or event.get("event_kind") or "").casefold()
        failure_family = str(event.get("failure_family") or "")
        if status != "failed" and "failed" not in hard_kind and failure_family in {"", "none"}:
            continue
        event_ref = _clean_event_ref(event)
        if not event_ref:
            continue
        command_class = str(event.get("command_class") or "")
        critical_family = str(event.get("critical_operation_family") or "")
        detail = (
            "verification_failure"
            if command_class in {"test", "check"} or critical_family == "test_check_command_result"
            else f"tool_failure_{failure_family or 'unknown'}"
        )
        rows.append(
            _base_row(
                signal_kind="tool_failure_texture",
                signal_detail=detail,
                origin="behavior_event",
                source_refs=[event_ref],
                event_refs=[event_ref],
                source_fingerprints=_fingerprints(event),
                role_scope="behavior_event",
                signal_labels=[
                    "tool_failure",
                    command_class or "tool",
                    failure_family or "unknown_failure",
                    detail,
                ],
            )
        )
    return rows


def _joined_event_refs(route_note: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for joined in route_note.get("joined_evidence_refs") or []:
        if not isinstance(joined, Mapping):
            continue
        source_ref = joined.get("source_ref")
        ref = dict(source_ref) if isinstance(source_ref, Mapping) else {}
        for key in ("event_id", "event_kind", "status", "command_class", "command_family", "failure_family"):
            value = joined.get(key)
            if value not in (None, "", []):
                ref[key] = value
        if ref:
            refs.append(ref)
    return refs


def _route_note_rows(route_notes: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route_note in route_notes:
        note_type = str(route_note.get("note_type") or "process_route").casefold()
        source_refs = [
            dict(item)
            for item in route_note.get("source_refs") or []
            if isinstance(item, Mapping)
        ]
        note_ref = route_note.get("note_source_ref")
        if isinstance(note_ref, Mapping):
            source_refs.append(dict(note_ref))
        event_refs = _joined_event_refs(route_note)
        if not source_refs and not event_refs:
            continue
        rows.append(
            _base_row(
                signal_kind="process_route_note",
                signal_detail=f"route_note_{note_type}",
                origin="route_note",
                source_refs=source_refs,
                event_refs=event_refs,
                source_fingerprints=_fingerprints(route_note),
                role_scope="process_navigation",
                signal_labels=[
                    "route_note",
                    note_type,
                    *[str(item) for item in route_note.get("reason_codes") or []][:4],
                ],
            )
        )
    return rows


def build_source_texture(
    messages: Iterable[Mapping[str, Any]],
    *,
    events: Iterable[Mapping[str, Any]] | None = None,
    route_notes: Iterable[Mapping[str, Any]] | None = None,
    max_rows: int = 200,
) -> list[dict[str, Any]]:
    """Return deterministic source-texture rows without serializing raw payloads."""

    rows = [
        *_message_rows(messages),
        *_event_rows(events or []),
        *_route_note_rows(route_notes or []),
    ]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        marker = row["texture_id"]
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
        if len(out) >= max(0, int(max_rows or 0)):
            break
    return out


def _ref_line(ref: Mapping[str, Any]) -> int | None:
    value = ref.get("line", ref.get("source_line"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _segment_contains_ref(segment: Mapping[str, Any], source_ref: Mapping[str, Any]) -> bool:
    ref_line = _ref_line(source_ref)
    start_line = _ref_line({"line": segment.get("start_line")})
    end_line = _ref_line({"line": segment.get("end_line")})
    if ref_line is not None and start_line is not None and end_line is not None:
        if start_line <= ref_line <= end_line:
            return True
    ref_message = source_ref.get("message_id")
    if ref_message:
        for seg_ref in segment.get("source_refs") or []:
            if isinstance(seg_ref, Mapping) and str(seg_ref.get("message_id") or "") == str(ref_message):
                return True
    return False


def _hint_confidence(texture_row: Mapping[str, Any]) -> float:
    kind = str(texture_row.get("signal_kind") or "")
    if kind in {"self_correction_signal", "tool_failure_texture"}:
        return 0.86
    if kind in {"abandoned_direction", "process_route_note"}:
        return 0.78
    return 0.64


def build_source_texture_boundary_hints(
    canonical_segments: Iterable[Mapping[str, Any]],
    texture_rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 64,
) -> list[dict[str, Any]]:
    """Project texture rows into optional read-model segment hints.

    These hints are derived ids that point back to canonical segment/source refs.
    They must not replace clean-source rows, mutate stable source ids, or grant
    claim authority. Consumers may use them to choose where to look next.
    """

    segments = [dict(segment) for segment in canonical_segments]
    hints: list[dict[str, Any]] = []
    boundary_kinds = {
        "self_correction_signal",
        "tool_failure_texture",
        "abandoned_direction",
        "uncertainty_or_frontier_signal",
        "process_route_note",
    }
    for row in texture_rows:
        signal_kind = str(row.get("signal_kind") or "")
        if str(row.get("truth_boundary") or "") != SOURCE_TEXTURE_BOUNDARY:
            continue
        if signal_kind not in boundary_kinds:
            continue
        refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, Mapping)]
        if not refs:
            continue
        for segment in segments:
            if not any(_segment_contains_ref(segment, ref) for ref in refs):
                continue
            canonical_id = str(segment.get("segment_id") or segment.get("id") or "segment")
            detail = str(row.get("signal_detail") or signal_kind)
            hint_id = stable_text_id("sthint", canonical_id, row.get("texture_id"), detail, length=20)
            hints.append(
                {
                    "kind": "aippocampus_source_texture_boundary_hint",
                    "hint_id": hint_id,
                    "derived_segment_id": f"texture_hint:{canonical_id}:{hint_id.rsplit('_', 1)[-1]}",
                    "canonical_segment_id": canonical_id,
                    "canonical_source_refs": _dedupe_refs(segment.get("source_refs") or [])[:4],
                    "source_refs": _dedupe_refs(refs)[:4],
                    "boundary_source": "source_texture",
                    "boundary_reason": detail,
                    "signal_kind": signal_kind,
                    "confidence": _hint_confidence(row),
                    "truth_boundary": "texture_hint_read_model_not_source_fact",
                    "read_model_only": True,
                    "canonical_source_ref_mutation_allowed": False,
                    "source_reopen_required_before_claim": True,
                }
            )
            break
        if len(hints) >= limit:
            break
    return hints


def write_source_texture_sidecar(
    output_dir: Path,
    rows: list[dict[str, Any]],
    *,
    source_session_id: str | None = None,
) -> Path:
    """Write `source-texture.jsonl` beside clean source."""

    path = output_dir / str(SOURCE_TEXTURE_POLICY["default_file"])
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for ordinal, item in enumerate(rows):
            item["texture_ordinal"] = ordinal
            item["source_session_id"] = source_session_id
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def attach_source_texture_profile_summary(
    profile_summary: dict[str, dict[str, Any]],
    path: Path,
) -> None:
    """Mark texture as private in redaction-profile summaries."""

    for profile, summary in profile_summary.items():
        if profile == "raw-private":
            summary["source_texture_jsonl"] = str(path)
            summary["source_texture_policy"] = {
                "projection": "canonical_private_sidecar",
                "canonical_source_replaced": False,
            }
        else:
            summary["source_texture_policy"] = {
                "projection": "omitted",
                "reason": "private_interpretation_sidecar",
                "canonical_source_replaced": False,
            }


def source_texture_health_summary(
    clean_source_dir: Path,
    clean_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Return health diagnostics without turning missing texture into staleness."""

    path = clean_source_dir / str(SOURCE_TEXTURE_POLICY["default_file"])
    manifest_count = clean_manifest.get("source_texture_count")
    row_count = int(manifest_count) if manifest_count is not None else _count_jsonl_rows(path)
    policy = clean_manifest.get("source_texture_policy") or {}
    return {
        "path": str(path),
        "exists": path.exists(),
        "row_count": row_count if path.exists() else 0,
        "rebuildable": True,
        "canonical_source": False,
        "truth_boundary": SOURCE_TEXTURE_BOUNDARY,
        "consumer_boundary": "interpretation_input_only",
        "policy_version": policy.get("version") or SOURCE_TEXTURE_POLICY["version"],
        "boundary": policy.get("boundary") or SOURCE_TEXTURE_POLICY["boundary"],
    }


def materialize_source_texture_sidecar(
    messages: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    route_notes: Iterable[Mapping[str, Any]],
    output_dir: Path,
    source_session_id: str | None,
    profile_summary: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = build_source_texture(messages, events=events, route_notes=route_notes)
    path = write_source_texture_sidecar(output_dir, rows, source_session_id=source_session_id)
    attach_source_texture_profile_summary(profile_summary, path)
    return {"path": str(path), "row_count": len(rows), "policy": SOURCE_TEXTURE_POLICY}


__all__ = [
    "SOURCE_TEXTURE_BOUNDARY",
    "SOURCE_TEXTURE_KIND",
    "SOURCE_TEXTURE_POLICY",
    "SOURCE_TEXTURE_SCHEMA_VERSION",
    "attach_source_texture_profile_summary",
    "build_source_texture",
    "materialize_source_texture_sidecar",
    "source_texture_health_summary",
    "write_source_texture_sidecar",
]
