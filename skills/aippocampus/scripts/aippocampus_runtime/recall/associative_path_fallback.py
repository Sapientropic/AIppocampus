"""Opt-in APW fallback adapter for agent recall misses.

APW diagnostics are useful only when they can become the next source-open
action. This module deliberately sits between the diagnostic walker and the
agent-recall foreground surface: it keeps default recall ranking untouched,
runs source-shape guards before projection, and returns a same-machine
request-index deepen request instead of exposing raw source refs in compact
JSON.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp import recall_navigation
from aippocampus_runtime.recall import agent_deepen_requests
from aippocampus_runtime.recall.associative_path_inputs import build_associative_path_diagnostic
from aippocampus_runtime.recall.associative_path_source_shape import (
    build_associative_path_source_shape,
)
from aippocampus_runtime.recall.query_policy import unique_preserve

KIND = "aippocampus_associative_path_recall_fallback"
SCHEMA_VERSION = 1


def _text(value: Any, limit: int = 120) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _code(value: Any, *, fallback: str = "", limit: int = 80) -> str:
    text = _text(value, limit).casefold().replace(" ", "_").replace("-", "_")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in {"_", ":"}).strip("_")
    return safe or fallback


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _refs(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list | tuple) else []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = recall_navigation._clean_ref(dict(row))  # noqa: SLF001 - shared source-ref normalizer.
        if not clean:
            continue
        marker = tuple(sorted((key, str(item)) for key, item in clean.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(clean)
        if len(refs) >= recall_navigation.MAX_HANDLE_REFS:
            break
    return refs


def _candidate_refs(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _refs(candidate.get("source_refs")) or _refs(candidate.get("event_refs"))


def _route_label(candidate: Mapping[str, Any]) -> str:
    terms = [str(term) for term in candidate.get("matched_terms") or [] if str(term).strip()]
    if terms:
        return "APW fallback: " + _text(", ".join(terms[:3]), 72)
    route_id = _text(candidate.get("route_id"), 60)
    return f"APW fallback: {route_id}" if route_id else "APW fallback route"


def _source_shape_projection(candidate: Mapping[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    route_id = _text(candidate.get("route_id"), 120) or _stable_id("apw", candidate)
    shaped = build_associative_path_source_shape(candidate, refs=refs, route_id=route_id)
    projection = shaped["projection"]
    return projection if isinstance(projection, dict) else {}


def _candidate_to_route(
    candidate: Mapping[str, Any],
    *,
    refs: list[dict[str, Any]],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    route_id = _text(candidate.get("route_id"), 120) or _stable_id("apw", candidate)
    public_route_id = route_id if route_id.startswith("apw:") else f"apw:{route_id}"
    reason_codes = unique_preserve(
        [
            "apw_opt_in_fallback",
            _code(projection.get("route_posture"), fallback="source_shape_guarded"),
            *[
                _code(code)
                for code in projection.get("triage_rank_reason_codes") or []
                if _code(code)
            ],
            *[
                _code(code)
                for code in candidate.get("reason_codes") or []
                if _code(code)
            ],
        ],
        limit=5,
    )
    return {
        "route_id": public_route_id,
        "kind": "associative_path",
        "handle": {
            "kind": "source_ref",
            "route_id": public_route_id,
            "source_refs": refs,
        },
        "route_label": _route_label(candidate),
        "route_topic": "associative_path_recovery",
        "matched_cue_family": "associative_path_fallback",
        "scope_bucket": "project_or_clean_source",
        "route_kind": "associative_path",
        "reopenable": True,
        "label_granularity": "associative_path_terms",
        "route_label_specificity_score": 0.7,
        "triage_rank_reason_codes": reason_codes,
        "risk_flags": unique_preserve(
            [str(flag) for flag in projection.get("risk_flags") or [] if str(flag).strip()],
            limit=6,
        ),
        "why_this_may_matter": (
            "APW found a source-ref-backed association after ordinary recall was weak; "
            "reopen the source before using it."
        ),
        "_selection_hint": {
            "source": "associative_path_walker",
            "why": reason_codes[0] if reason_codes else "apw_opt_in_fallback",
        },
    }


def _abstention(
    *,
    diagnostic: Mapping[str, Any],
    reason_code: str,
    ordinary_status: str,
) -> dict[str, Any]:
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "abstained",
        "decision": str(diagnostic.get("decision") or "abstain"),
        "ordinary_recall_status": ordinary_status,
        "opt_in_required": True,
        "applied_to_default_ranking": False,
        "reason_codes": unique_preserve(
            [
                reason_code,
                *[str(code) for code in diagnostic.get("reason_codes") or [] if str(code).strip()],
            ],
            limit=8,
        ),
        "summary": "APW fallback was requested, but it did not produce a source-reopenable route.",
        "source_reopen_required_before_claim": True,
    }


def build_associative_path_agent_fallback(
    *,
    query: str,
    ordinary_status: str,
    request_index: int,
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    semantic_bridge_path: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return a compact-safe fallback card and optional deepen request."""

    diagnostic = build_associative_path_diagnostic(
        query=query,
        cwd=cwd,
        sidecar_dir=sidecar_dir,
        semantic_bridge_path=semantic_bridge_path,
        navigation_path=navigation_path,
        active_lock_path=active_lock_path,
        feedback_path=feedback_path,
    )
    candidates = [row for row in diagnostic.get("top_candidates") or [] if isinstance(row, Mapping)]
    if str(diagnostic.get("decision") or "") != "route_candidates" or not candidates:
        return (
            _abstention(
                diagnostic=diagnostic,
                reason_code="apw_no_route_candidate",
                ordinary_status=ordinary_status,
            ),
            None,
        )
    for candidate in candidates:
        refs = _candidate_refs(candidate)
        if not refs:
            continue
        projection = _source_shape_projection(candidate, refs)
        if str(projection.get("action_grammar") or "") == "ignore_or_blocked":
            continue
        if int(projection.get("source_ref_count") or 0) <= 0:
            continue
        route = _candidate_to_route(candidate, refs=refs, projection=projection)
        request = agent_deepen_requests.deepen_request_for_route(
            route,
            {
                "route_id": route["route_id"],
                "deepen_route_id": f"deepen:{route['route_id']}",
            },
            request_index=max(1, int(request_index or 1)),
        )
        card = {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "status": "route_candidate",
            "decision": "deepen_associative_path_fallback",
            "ordinary_recall_status": ordinary_status,
            "opt_in_required": True,
            "applied_to_default_ranking": False,
            "request_index": request["request_index"],
            "label": route["route_label"],
            "why_this_route": route["why_this_may_matter"],
            "route_posture": projection.get("route_posture"),
            "action_grammar": projection.get("action_grammar"),
            "risk_flags": route.get("risk_flags") or [],
            "reason_codes": route.get("triage_rank_reason_codes") or [],
            "source_shape_id": projection.get("source_shape_id"),
            "source_shape_guard_reasons": projection.get("triage_rank_reason_codes") or [],
            "source_reopen_required_before_claim": True,
            "source_shape_guarded": True,
        }
        return card, request
    return (
        _abstention(
            diagnostic=diagnostic,
            reason_code="apw_source_shape_blocked_or_source_free",
            ordinary_status=ordinary_status,
        ),
        None,
    )


def maybe_append_associative_path_fallback(
    *,
    include_associative_fallback: bool,
    query: str,
    ordinary_status: str,
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    triage_metrics: Mapping[str, Any],
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    semantic_bridge_path: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Append an APW deepen request only for explicit weak/silent recall recovery."""

    should_run = include_associative_fallback and (
        not memory_packets
        or not deepen_requests
        or float(triage_metrics.get("route_label_specificity_floor") or 0.0) <= 0.0
        or float(triage_metrics.get("packet_triage_distinctiveness") or 0.0) < 0.5
    )
    if not should_run:
        return None
    fallback, request = build_associative_path_agent_fallback(
        query=query,
        ordinary_status=ordinary_status,
        request_index=len(deepen_requests) + 1,
        cwd=cwd,
        sidecar_dir=sidecar_dir,
        semantic_bridge_path=semantic_bridge_path,
        navigation_path=navigation_path,
        active_lock_path=active_lock_path,
        feedback_path=feedback_path,
    )
    if request is not None:
        deepen_requests.append(request)
    return fallback


def add_cli_arguments(parser: Any) -> None:
    parser.add_argument(
        "--apw-fallback",
        "--include-associative-fallback",
        action="store_true",
        dest="include_associative_fallback",
        help="Opt in to APW source-shape fallback when ordinary recall is silent or weak.",
    )
    parser.add_argument("--apw-sidecar-dir")
    parser.add_argument("--apw-semantic-bridge-path")
    parser.add_argument("--apw-navigation-path")
    parser.add_argument("--apw-active-lock-path")
    parser.add_argument("--apw-feedback-path")


def cli_kwargs(args: Any) -> dict[str, Any]:
    return {
        "include_associative_fallback": bool(getattr(args, "include_associative_fallback", False)),
        "associative_path_sidecar_dir": getattr(args, "apw_sidecar_dir", None),
        "associative_path_bridge_path": getattr(args, "apw_semantic_bridge_path", None),
        "associative_path_navigation_path": getattr(args, "apw_navigation_path", None),
        "associative_path_active_lock_path": getattr(args, "apw_active_lock_path", None),
        "associative_path_feedback_path": getattr(args, "apw_feedback_path", None),
    }


def route_count(card: Mapping[str, Any] | None) -> int:
    return int(isinstance(card, Mapping) and card.get("status") == "route_candidate")


__all__ = [
    "add_cli_arguments",
    "build_associative_path_agent_fallback",
    "cli_kwargs",
    "maybe_append_associative_path_fallback",
    "route_count",
]
