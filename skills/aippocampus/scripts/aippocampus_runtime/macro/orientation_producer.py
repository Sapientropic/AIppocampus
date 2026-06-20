"""Staged Macro-orientation producer.

Macro consumers can use project state once it exists, but router observations
must not mutate that state on the hot path. This module turns eligible
source-backed observations into reviewable candidates, then provides one
explicit promotion helper that appends a durable state row only after review.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.macro import momentum as momentum_runtime
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.macro import three_powers
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

CANDIDATE_KIND = "macro_orientation_state_candidate"
CANDIDATE_SCHEMA_VERSION = 1
DEFAULT_CANDIDATE_QUEUE = Path(".aippocampus") / "macro-orientation-candidates.jsonl"


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _safe_text(value: Any, limit: int = 120) -> str:
    text = core.compact_text(str(value or "").strip(), limit)
    return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-", ":", "#", ".", "/"})


def _project_from_scope(scope: Any, project: str | None) -> str:
    if project and str(project).strip():
        return str(project).strip()
    text = str(scope or "").strip()
    if text.startswith("project:") and text[len("project:") :].strip():
        return text[len("project:") :].strip()
    return "AIppocampus"


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return round(float(value), 6)
    try:
        return round(float(str(value)), 6)
    except (TypeError, ValueError):
        return 0.0


def _momentum_basis(signals: Mapping[str, Any]) -> dict[str, float]:
    return momentum_runtime.normalize_momentum_basis(
        {
            "support_delta": _float(signals.get("support_delta")),
            "route_success_delta": _float(signals.get("route_success_delta")),
            "counter_evidence_delta": _float(signals.get("counter_evidence_delta")),
            "staleness_delta": _float(signals.get("staleness_delta")),
            "user_correction_delta": _float(signals.get("user_correction_delta")),
        }
    )


def _source_refs(source_event_refs: Sequence[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in source_event_refs:
        text = _safe_text(item, 160)
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append({"source_id": text})
    return refs


def build_candidate_from_router_observation(
    observation: Mapping[str, Any],
    *,
    project: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a reviewable candidate from an eligible router observation."""

    source_event_refs = [
        item
        for item in observation.get("source_event_refs") or []
        if str(item or "").strip()
    ]
    candidate_update = observation.get("candidate_macro_update")
    update = candidate_update if isinstance(candidate_update, Mapping) else {}
    if observation.get("kind") != "router_macro_observation":
        return _public_payload(
            {
                "kind": CANDIDATE_KIND,
                "schema_version": CANDIDATE_SCHEMA_VERSION,
                "status": "suppressed_invalid_observation",
                "candidate_ready": False,
                "reason": "expected router_macro_observation",
            }
        )
    if not update.get("eligible_for_macro_update") or not source_event_refs:
        return _public_payload(
            {
                "kind": CANDIDATE_KIND,
                "schema_version": CANDIDATE_SCHEMA_VERSION,
                "status": "suppressed_missing_source_refs",
                "candidate_ready": False,
                "reason": "macro state candidates require source_event_refs",
                "source_boundary": {
                    "source_refs_required_before_macro_update": True,
                    "hot_path_write_allowed": False,
                },
            }
        )

    try:
        active_layer = three_powers.normalize_layer(update.get("active_layer") or "human")
    except ValueError:
        active_layer = "human"
    signals = observation.get("signals")
    signal_map = signals if isinstance(signals, Mapping) else {}
    basis = _momentum_basis(signal_map)
    momentum_block = momentum_runtime.build_momentum_block(basis)
    refs = _source_refs(source_event_refs)
    project_name = _project_from_scope(observation.get("scope"), project)
    created = created_at or macro_state.utc_now_iso()
    return _public_payload(
        {
            "kind": CANDIDATE_KIND,
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "status": "candidate_ready",
            "candidate_ready": True,
            "created_at": created,
            "project": project_name,
            "scope": {"kind": "project", "project": project_name},
            "authority_level": macro_state.AUTHORITY_LEVEL,
            "action_grammar": macro_state.ACTION_GRAMMAR,
            "claim_permission": macro_state.CLAIM_PERMISSION,
            "source_refs": refs,
            "active_layer": active_layer,
            "active_layer_source": "router_observation",
            "momentum_basis": basis,
            "momentum": {
                "phase": momentum_block.get("phase"),
                "direction": momentum_block.get("direction"),
                "route_policy": momentum_block.get("route_policy"),
            },
            "router_observation_summary": {
                "movement_state": update.get("movement_state"),
                "reason_codes": [
                    _safe_text(code, 80)
                    for code in update.get("reason_codes") or []
                    if _safe_text(code, 80)
                ][:6],
                "observed_layer_distribution": observation.get("observed_layer_distribution") or {},
            },
            "review": {
                "status": "pending_review",
                "required_before_write": True,
                "allowed_statuses": ["reviewed", "accepted", "approved"],
            },
            "promotion_plan": {
                "target": ".aippocampus/macro-orientation.jsonl",
                "write_helper": "promote_reviewed_candidate_to_state",
                "hot_path_write_allowed": False,
                "total_hexagram_status": "not_produced",
                "active_layer_and_momentum_only": True,
            },
            "source_boundary": {
                "navigation_only_not_fact": True,
                "candidate_is_not_durable_state": True,
                "source_refs_required_before_macro_update": True,
                "raw_private_text_serialized": False,
                "local_paths_serialized": False,
            },
        }
    )


def review_macro_orientation_candidate(
    candidate: Mapping[str, Any],
    *,
    reviewed_by: str = "operator",
    review_reason: str = "source-backed router observation accepted for navigation-only macro state",
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    if candidate.get("kind") != CANDIDATE_KIND or not candidate.get("candidate_ready"):
        raise ValueError("only ready macro orientation candidates can be reviewed")
    return _public_payload(
        {
            **dict(candidate),
            "review": {
                "status": "reviewed",
                "reviewed_by": _safe_text(reviewed_by, 80) or "operator",
                "review_reason": core.compact_text(review_reason, 220),
                "reviewed_at": reviewed_at or macro_state.utc_now_iso(),
                "required_before_write": True,
            },
        }
    )


def stage_macro_orientation_candidate(path: str | Path, candidate: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("kind") != CANDIDATE_KIND or not candidate.get("candidate_ready"):
        return {
            "kind": "macro_orientation_candidate_stage_result",
            "status": "not_staged",
            "wrote_candidate": False,
            "reason": str(candidate.get("status") or "candidate_not_ready"),
        }
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True) + "\n")
    return _public_payload(
        {
            "kind": "macro_orientation_candidate_stage_result",
            "status": "staged",
            "wrote_candidate": True,
            "candidate_queue_label": DEFAULT_CANDIDATE_QUEUE.as_posix(),
            "review_required_before_state_write": True,
        }
    )


def _review_allows_write(candidate: Mapping[str, Any]) -> bool:
    review = candidate.get("review")
    review_map = review if isinstance(review, Mapping) else {}
    return str(review_map.get("status") or "") in {"reviewed", "accepted", "approved"}


def promote_reviewed_candidate_to_state(
    candidate: Mapping[str, Any],
    *,
    output_path: str | Path,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Append a durable state row from a reviewed candidate."""

    if candidate.get("kind") != CANDIDATE_KIND or not candidate.get("candidate_ready"):
        raise ValueError("macro orientation candidate is not ready")
    if not _review_allows_write(candidate):
        raise ValueError("macro orientation candidate requires review before write")
    source_refs = [ref for ref in candidate.get("source_refs") or [] if isinstance(ref, Mapping)]
    if not source_refs:
        raise ValueError("macro orientation candidate requires source refs")
    project = str(candidate.get("project") or "AIppocampus").strip() or "AIppocampus"
    basis = candidate.get("momentum_basis")
    basis_map = basis if isinstance(basis, Mapping) else {}
    state_row = macro_state.build_macro_orientation_state(
        project=project,
        hexagram="坤",
        changing_lines=(),
        source_refs=source_refs,
        input_signal_scales=("project_event",),
        promotion_reason="project_source_event",
        updated_at=updated_at or macro_state.utc_now_iso(),
        active_layer=str(candidate.get("active_layer") or "human"),
        momentum={"basis": basis_map},
    )
    existing_trace = state_row.get("derivation_trace")
    derivation_trace = (
        [str(item) for item in existing_trace]
        if isinstance(existing_trace, Sequence) and not isinstance(existing_trace, str | bytes)
        else []
    )
    state_row = {
        **state_row,
        "producer": {
            "kind": "macro_orientation_staged_producer",
            "source_candidate_kind": CANDIDATE_KIND,
            "active_layer_source": candidate.get("active_layer_source"),
            "momentum_source": "source_backed_router_observation_deltas",
            "total_hexagram_status": "not_produced",
            "line_signal_reducer_status": "unavailable",
            "review_status": (candidate.get("review") or {}).get("status")
            if isinstance(candidate.get("review"), Mapping)
            else "reviewed",
        },
        "derivation_trace": [
            *derivation_trace,
            "active_layer_and_momentum_promoted_from_reviewed_router_observation",
            "total_hexagram_not_produced_by_this_path",
        ],
    }
    target = Path(output_path).expanduser().resolve()
    macro_state.append_macro_orientation_state(target, state_row)
    return _public_payload(
        {
            "kind": "macro_orientation_candidate_promotion",
            "status": "state_written",
            "wrote_state": True,
            "state_status": macro_state.validate_macro_orientation_state(state_row),
            "state": state_row,
            "output_label": ".aippocampus/macro-orientation.jsonl",
            "source_boundary": {
                "navigation_only_not_fact": True,
                "review_required_before_write": True,
                "source_reopen_required_before_claims": True,
                "raw_private_text_serialized": False,
                "local_paths_serialized": False,
            },
        }
    )


def default_candidate_queue_path(cwd: str | Path | None = None) -> Path:
    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    return root / DEFAULT_CANDIDATE_QUEUE


__all__ = [
    "CANDIDATE_KIND",
    "CANDIDATE_SCHEMA_VERSION",
    "DEFAULT_CANDIDATE_QUEUE",
    "build_candidate_from_router_observation",
    "default_candidate_queue_path",
    "promote_reviewed_candidate_to_state",
    "review_macro_orientation_candidate",
    "stage_macro_orientation_candidate",
]
