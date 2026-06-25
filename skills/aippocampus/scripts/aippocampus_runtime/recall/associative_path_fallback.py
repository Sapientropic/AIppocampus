"""APW recall fallback adapter for weak or silent agent recall.

APW diagnostics are useful only when they can become the next source-open
action. This module deliberately sits between the diagnostic walker and the
agent-recall foreground surface: it keeps default recall ranking untouched,
runs source-shape guards before projection, and returns a same-machine
request-index deepen request instead of exposing raw source refs in compact
JSON. The current promotion is deliberately narrow: APW may surface as a
secondary recovery action for no-route or weak-recall flows, but it never
reorders ordinary recall routes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp import recall_navigation
from aippocampus_runtime.recall import agent_deepen_requests, apw_route_identity
from aippocampus_runtime.recall.associative_path_fallback_policy import (
    MODE_OFF,
    MODE_OPT_IN,
    MODE_SEMI_DEFAULT_RECOVERY,
    PROMOTION_MODE_ENV,
    has_associative_path_candidate_input,
    recall_fallback_policy,
)
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


def _source_ref_digest(refs: list[dict[str, Any]]) -> str:
    return apw_route_identity.source_ref_digest(refs)


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
        return "APW source route: " + _text(" / ".join(terms[:3]), 90)
    route_id = _text(candidate.get("route_id"), 60)
    return f"APW source route: {route_id}" if route_id else "APW source route"


def _source_shape_projection(candidate: Mapping[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    route_id = _text(candidate.get("route_id"), 120) or core.stable_json_id("apw", candidate, length=16)
    shaped = build_associative_path_source_shape(candidate, refs=refs, route_id=route_id)
    projection = shaped["projection"]
    return projection if isinstance(projection, dict) else {}


def _candidate_to_route(
    candidate: Mapping[str, Any],
    *,
    refs: list[dict[str, Any]],
    projection: Mapping[str, Any],
    reason_code: str,
) -> dict[str, Any]:
    route_id = _text(candidate.get("route_id"), 120) or core.stable_json_id("apw", candidate, length=16)
    public_route_id = route_id if route_id.startswith("apw:") else f"apw:{route_id}"
    reason_codes = unique_preserve(
        [
            reason_code,
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
    matched_terms = unique_preserve(
        [str(term) for term in candidate.get("matched_terms") or [] if str(term).strip()],
        limit=5,
    )
    label = _route_label(candidate)
    source_ref_digest = _source_ref_digest(refs)
    apw_identity = apw_route_identity.route_identity_envelope(
        public_route_id=public_route_id,
        apw_candidate_route_id=route_id,
        apw_candidate_id=_text(candidate.get("candidate_id"), 120),
        source_refs=refs,
        source_ref_digest_value=source_ref_digest,
        matched_cue_anchors=matched_terms,
        candidate_source_kind=candidate.get("candidate_source_kind"),
        source_shape_posture=projection.get("route_posture"),
    )
    return {
        "route_id": public_route_id,
        "kind": "associative_path",
        "handle": {
            "kind": "source_ref",
            "route_id": public_route_id,
            "source_refs": refs,
        },
        "route_label": label,
        "route_topic": "associative_path_recovery",
        "matched_cue_family": "associative_path_fallback",
        "matched_cue_anchors": matched_terms,
        "source_anchor_gate": candidate.get("source_anchor_gate"),
        "apw_candidate_route_id": route_id,
        "apw_candidate_id": _text(candidate.get("candidate_id"), 120),
        "source_ref_digest": source_ref_digest,
        "selected_source_ref_count": len(refs),
        "apw_route_identity": apw_identity,
        "candidate_source_kind": candidate.get("candidate_source_kind"),
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
            "APW matched distinctive cue anchors after ordinary recall was weak; "
            "reopen the source before using it."
        ),
        "_selection_hint": {
            "source": "associative_path_walker",
            "why": reason_codes[0] if reason_codes else reason_code,
        },
    }


def _abstention(
    *,
    diagnostic: Mapping[str, Any],
    reason_code: str,
    ordinary_status: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = core.dict_or_empty(diagnostic.get("metrics"))
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "abstained",
        "decision": str(diagnostic.get("decision") or "abstain"),
        "ordinary_recall_status": ordinary_status,
        "current_build_posture": policy.get("current_build_posture"),
        "policy_mode": policy.get("promotion_mode"),
        "promotion_surface": policy.get("promotion_surface"),
        "route_choice_posture": (
            "associative_path_opt_in_fallback"
            if policy.get("opt_in_required_for_this_run")
            else "associative_path_semi_default_recovery"
        ),
        "opt_in_required": bool(policy.get("opt_in_required_for_this_run", True)),
        "applied_to_default_ranking": False,
        "rollback_env": policy.get("rollback_env"),
        "reason_codes": unique_preserve(
            [
                str(policy.get("run_reason") or ""),
                reason_code,
                *[str(code) for code in diagnostic.get("reason_codes") or [] if str(code).strip()],
            ],
            limit=8,
        ),
        "registry_match_count": int(metrics.get("registry_match_count") or 0),
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
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    semantic_bridge_path: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
    policy: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return a compact-safe fallback card and optional deepen request."""

    policy = dict(policy or {})
    if not policy:
        policy = recall_fallback_policy(
            include_associative_fallback=True,
            query=query,
            memory_packets=[],
            deepen_requests=[],
            triage_metrics={},
            cwd=cwd,
            sidecar_dir=sidecar_dir,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            navigation_path=navigation_path,
            active_lock_path=active_lock_path,
        )
    reason_code = str(policy.get("run_reason") or "apw_opt_in_fallback")
    diagnostic = build_associative_path_diagnostic(
        query=query,
        cwd=cwd,
        sidecar_dir=sidecar_dir,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
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
                policy=policy,
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
        route = _candidate_to_route(
            candidate,
            refs=refs,
            projection=projection,
            reason_code=reason_code,
        )
        request = agent_deepen_requests.deepen_request_for_route(
            route,
            {
                "route_id": route["route_id"],
                "deepen_route_id": f"deepen:{route['route_id']}",
            },
            request_index=max(1, int(request_index or 1)),
        )
        request.update(
            {
                "matched_cue_family": "associative_path_fallback",
                "matched_cue_anchors": route.get("matched_cue_anchors") or [],
                "candidate_source_kind": route.get("candidate_source_kind"),
                "source_ref_digest": route.get("source_ref_digest"),
                "selected_source_ref_count": route.get("selected_source_ref_count"),
                "source_anchor_gate": route.get("source_anchor_gate"),
                "apw_candidate_route_id": route.get("apw_candidate_route_id"),
                "apw_candidate_id": route.get("apw_candidate_id"),
                "apw_route_identity": route.get("apw_route_identity"),
            }
        )
        card = {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "status": "route_candidate",
            "decision": "deepen_associative_path_fallback",
            "ordinary_recall_status": ordinary_status,
            "current_build_posture": policy.get("current_build_posture"),
            "policy_mode": policy.get("promotion_mode"),
            "promotion_surface": policy.get("promotion_surface"),
            "promotion_gate": policy.get("promotion_gate"),
            "route_choice_posture": (
                "associative_path_opt_in_fallback"
                if policy.get("opt_in_required_for_this_run")
                else "associative_path_semi_default_recovery"
            ),
            "opt_in_required": bool(policy.get("opt_in_required_for_this_run", True)),
            "applied_to_default_ranking": False,
            "rollback_env": policy.get("rollback_env"),
            "rollback_behavior": policy.get("rollback_behavior"),
            "request_index": request["request_index"],
            "route_id": route["route_id"],
            "apw_candidate_route_id": route.get("apw_candidate_route_id"),
            "apw_candidate_id": route.get("apw_candidate_id"),
            "source_ref_digest": route.get("source_ref_digest"),
            "selected_source_ref_count": route.get("selected_source_ref_count"),
            "source_anchor_gate": route.get("source_anchor_gate"),
            "apw_route_identity": route.get("apw_route_identity"),
            "label": route["route_label"],
            "why_this_route": route["why_this_may_matter"],
            "matched_cue_anchors": route.get("matched_cue_anchors") or [],
            "candidate_source_kind": route.get("candidate_source_kind"),
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
                policy=policy,
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
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    semantic_bridge_path: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append an APW deepen request for eligible weak/silent recall recovery."""

    policy = dict(
        policy
        or recall_fallback_policy(
            include_associative_fallback=include_associative_fallback,
            query=query,
            memory_packets=memory_packets,
            deepen_requests=deepen_requests,
            triage_metrics=triage_metrics,
            cwd=cwd,
            sidecar_dir=sidecar_dir,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            navigation_path=navigation_path,
            active_lock_path=active_lock_path,
        )
    )
    if not policy.get("run_fallback"):
        return None
    fallback, request = build_associative_path_agent_fallback(
        query=query,
        ordinary_status=ordinary_status,
        request_index=len(deepen_requests) + 1,
        cwd=cwd,
        sidecar_dir=sidecar_dir,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        semantic_bridge_path=semantic_bridge_path,
        navigation_path=navigation_path,
        active_lock_path=active_lock_path,
        feedback_path=feedback_path,
        policy=policy,
    )
    if request is not None:
        deepen_requests.append(request)
    return fallback


def maybe_append_associative_path_fallback_with_policy(
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Compute APW policy once, append the eligible request, and return both."""

    policy = recall_fallback_policy(
        include_associative_fallback=bool(kwargs["include_associative_fallback"]),
        query=str(kwargs.get("query") or ""),
        memory_packets=kwargs["memory_packets"],
        deepen_requests=kwargs["deepen_requests"],
        triage_metrics=kwargs["triage_metrics"],
        cwd=kwargs.get("cwd"),
        sidecar_dir=kwargs.get("sidecar_dir"),
        clean_source_dir=kwargs.get("clean_source_dir"),
        registry_dir=kwargs.get("registry_dir"),
        navigation_path=kwargs.get("navigation_path"),
        active_lock_path=kwargs.get("active_lock_path"),
    )
    fallback = maybe_append_associative_path_fallback(**kwargs, policy=policy)
    return policy, fallback


def recall_fallback_metrics(
    include_associative_fallback: bool,
    policy: Mapping[str, Any],
    fallback: Mapping[str, Any] | None,
) -> dict[str, Any]:
    run_reason = str(policy.get("run_reason") or "")
    return {
        "associative_path_fallback_policy_mode": policy.get("promotion_mode"),
        "associative_path_fallback_requested": bool(include_associative_fallback),
        "associative_path_fallback_run": bool(policy.get("run_fallback")),
        "associative_path_fallback_semidefault_attempted": (
            bool(policy.get("run_fallback")) and run_reason == "apw_semi_default_recovery"
        ),
        "associative_path_candidate_input_available": bool(
            policy.get("apw_candidate_input_available")
        ),
        "associative_path_fallback_route_count": route_count(fallback),
    }


def add_cli_arguments(parser: Any) -> None:
    parser.add_argument(
        "--apw-fallback",
        "--include-associative-fallback",
        action="store_true",
        dest="include_associative_fallback",
        help=(
            "Request APW source-shape fallback when ordinary recall is silent or weak. "
            f"Default promotion policy is controlled by {PROMOTION_MODE_ENV}."
        ),
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
    "MODE_OFF",
    "MODE_OPT_IN",
    "MODE_SEMI_DEFAULT_RECOVERY",
    "PROMOTION_MODE_ENV",
    "add_cli_arguments",
    "build_associative_path_agent_fallback",
    "cli_kwargs",
    "has_associative_path_candidate_input",
    "maybe_append_associative_path_fallback",
    "maybe_append_associative_path_fallback_with_policy",
    "recall_fallback_metrics",
    "recall_fallback_policy",
    "route_count",
]
