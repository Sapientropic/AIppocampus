"""Fast/deep foreground recall channel diagnostics.

The prompt hook has two very different time horizons. Fast channel material is
local, source-routed, and safe to keep available on every prompt. Deep channel
material may include semantic or concept expansion and must stay diagnostic
until it rejoins stable source refs. Keep this module projection-only: it
labels existing candidates and degradation state, but it does not promote
source-free model output into evidence.
"""

from __future__ import annotations

from typing import Any


def _thread_key(candidate: dict[str, Any]) -> str:
    return str(candidate.get("thread_key") or candidate.get("id") or "").strip()


def _source_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in candidate.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        refs.append(
            {
                "thread_key": str(ref.get("thread_key") or _thread_key(candidate)),
                "line": ref.get("line") or ref.get("source_line"),
            }
        )
    return refs


def _candidate_channel(
    candidate: dict[str, Any],
    *,
    concept_expansions: list[dict[str, Any]],
) -> str:
    if candidate.get("hot_path_source") or candidate.get("semantic_trigger_source"):
        return "fast"
    if concept_expansions:
        return "deep"
    return "fast"


def _candidate_reason_codes(
    candidate: dict[str, Any],
    *,
    channel: str,
    concept_expansions: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    hot_path_reason = str(candidate.get("hot_path_reason") or "").strip()
    if hot_path_reason:
        reasons.append(f"hot_path:{hot_path_reason}")
    if candidate.get("semantic_trigger_source"):
        reasons.append("semantic_trigger_source_ref")
    if candidate.get("probe_score"):
        reasons.append("clean_source_probe_rerank")
    if channel == "deep" and concept_expansions:
        reasons.append("concept_graph_expansion")
    if not reasons:
        reasons.append("registry_overlap")
    return reasons


def _candidate_envelope(
    candidate: dict[str, Any],
    *,
    concept_expansions: list[dict[str, Any]],
) -> dict[str, Any]:
    channel = _candidate_channel(candidate, concept_expansions=concept_expansions)
    refs = _source_refs(candidate)
    return {
        "channel": channel,
        "thread_key": _thread_key(candidate),
        "source_refs": refs,
        "reopen_route": bool(refs or _thread_key(candidate)),
        "reason_codes": _candidate_reason_codes(
            candidate, channel=channel, concept_expansions=concept_expansions
        ),
    }


def _semantic_timeout(semantic_result: dict[str, Any] | None) -> bool:
    if not semantic_result:
        return False
    reason = str(semantic_result.get("availability_reason") or "").casefold()
    diagnostic = str(semantic_result.get("diagnostic") or "").casefold()
    return "timeout" in reason or "timeout" in diagnostic


def _semantic_available(semantic_result: dict[str, Any] | None) -> bool:
    return bool(semantic_result and semantic_result.get("available"))


def _semantic_source_free_route(
    semantic_result: dict[str, Any] | None,
    *,
    evidence: list[dict[str, Any]],
) -> bool:
    if semantic_result is None or not _semantic_available(semantic_result):
        return False
    decision = str(semantic_result.get("decision") or "").casefold()
    intent = str(semantic_result.get("intent") or "").casefold()
    return not evidence and (decision in {"evidence", "scent"} or "source" in intent)


def _deep_reason_codes(
    *,
    semantic_result: dict[str, Any] | None,
    concept_expansions: list[dict[str, Any]],
    effective_use_semantic_gate: bool,
    evidence: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if _semantic_timeout(semantic_result):
        reasons.append("semantic_gate_timeout")
    elif _semantic_available(semantic_result):
        assert semantic_result is not None
        decision = str(semantic_result.get("decision") or "available").casefold()
        reasons.append(f"semantic_gate_{decision}")
        if _semantic_source_free_route(semantic_result, evidence=evidence):
            reasons.append("semantic_gate_source_free_route")
    elif not effective_use_semantic_gate:
        reasons.append("semantic_gate_skipped")
    else:
        reasons.append("semantic_gate_no_route")
    if concept_expansions:
        reasons.append("concept_graph_expansion")
    return reasons


def _deep_status(
    *,
    semantic_result: dict[str, Any] | None,
    concept_expansions: list[dict[str, Any]],
    deep_candidates: list[dict[str, Any]],
    source_free_candidate_count: int,
) -> str:
    if _semantic_timeout(semantic_result):
        return "timeout"
    if deep_candidates or concept_expansions or source_free_candidate_count:
        return "hit"
    return "skip"


def _deadline_diagnostic(status: str, route_delivery_state: dict[str, Any]) -> dict[str, Any]:
    max_elapsed_ms = route_delivery_state.get("max_elapsed_ms")
    if status == "timeout":
        return {
            "status": "degraded",
            "reason": "semantic_timeout",
            "max_elapsed_ms": max_elapsed_ms,
        }
    if max_elapsed_ms is None:
        return {"status": "not_bounded", "max_elapsed_ms": None}
    return {"status": "within_budget", "max_elapsed_ms": max_elapsed_ms}


def recall_channel_envelope(
    *,
    candidates: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    semantic_result: dict[str, Any] | None,
    concept_expansions: list[dict[str, Any]],
    hot_path_funnel: dict[str, Any],
    route_delivery_state: dict[str, Any],
) -> dict[str, Any]:
    candidate_envelopes = [
        _candidate_envelope(candidate, concept_expansions=concept_expansions)
        for candidate in candidates
    ]
    fast_candidates = [item for item in candidate_envelopes if item["channel"] == "fast"]
    deep_candidates = [item for item in candidate_envelopes if item["channel"] == "deep"]
    effective_use_semantic_gate = bool(route_delivery_state.get("effective_use_semantic_gate"))
    source_free_candidate_count = (
        1 if _semantic_source_free_route(semantic_result, evidence=evidence) else 0
    )
    deep_status = _deep_status(
        semantic_result=semantic_result,
        concept_expansions=concept_expansions,
        deep_candidates=deep_candidates,
        source_free_candidate_count=source_free_candidate_count,
    )
    return {
        "fast": {
            "status": "hit" if fast_candidates else "skip",
            "candidate_count": len(fast_candidates),
            "candidates": fast_candidates,
            "reason_codes": sorted(
                {reason for item in fast_candidates for reason in item["reason_codes"]}
            )
            or ["no_fast_candidate"],
            "deadline": {"status": "local_only"},
            "hot_path_decision": hot_path_funnel.get("decision"),
        },
        "deep": {
            "status": deep_status,
            "candidate_count": len(deep_candidates),
            "candidates": deep_candidates,
            "reason_codes": _deep_reason_codes(
                semantic_result=semantic_result,
                concept_expansions=concept_expansions,
                effective_use_semantic_gate=effective_use_semantic_gate,
                evidence=evidence,
            ),
            "deadline": _deadline_diagnostic(deep_status, route_delivery_state),
            "source_free_candidate_count": source_free_candidate_count,
            "source_free_evidence_promotion": False,
            "blocked_fast_channel": False,
        },
    }


__all__ = ["recall_channel_envelope"]
