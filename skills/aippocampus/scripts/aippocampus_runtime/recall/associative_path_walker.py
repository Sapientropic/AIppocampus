"""Deterministic source-backed Associative Path Walker.

The walker is a navigation producer, not a truth engine. It explores a tiny
source-reopenable path budget across existing candidates and semantic bridge
rows, then returns either a few reopenable route candidates or a tighten-cue
abstention.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.recall import apw_route_identity, authority
from aippocampus_runtime.recall.query_policy import normalize_term, unique_preserve
from aippocampus_runtime.recall.semantic_bridge_map import reduce_semantic_bridge_candidates

SCHEMA_VERSION = 1
GENERIC_TERMS = {
    "agent",
    "context",
    "conversation",
    "issue",
    "memory",
    "project",
    "recall",
    "route",
    "search",
    "source",
    "task",
    "thread",
    "回忆",
    "记忆",
    "检索",
    "线索",
    "项目",
    "上下文",
}
PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}
STALE_STATUSES = {"stale", "superseded", "refuted", "retired", "archived", "expired"}
NEGATIVE_OUTCOMES = {"wrong_route_drag", "wrong_route", "ignored", "blocked", "superseded", "expired"}
POSITIVE_OUTCOMES = {"source_reopen_success", "reopened_deepened", "user_confirmed"}
DEFAULT_SAFE_SCOPE = "public_default"
FRONTIER_POLICY_NAME = "bounded_associative_frontier"


def decide_associative_frontier_step(
    *,
    direct_match: bool,
    bridge_hit_count: int,
    has_source_signal: bool,
    has_route_handle: bool,
    private_or_stale: bool = False,
    negative_feedback: bool = False,
    generic_only: bool = False,
) -> dict[str, Any]:
    """Return the bounded APW exploration decision for one frontier candidate.

    The policy is intentionally navigation-only. It decides whether a candidate
    can keep exploring toward a source reopen, must stay diagnostic/shadowed, or
    should abstain. Do not add factual confidence here; source truth starts only
    after a source window is reopened.
    """

    if private_or_stale:
        return {
            "action": "block",
            "route_posture": "blocked",
            "reason_codes": ["path_blocked_private_or_stale"],
        }
    if negative_feedback:
        return {
            "action": "shadow",
            "route_posture": "shadowed",
            "reason_codes": ["negative_feedback_evaporated"],
        }
    if generic_only:
        return {
            "action": "abstain",
            "route_posture": "diagnostic_only",
            "reason_codes": ["generic_only_path_evaporated"],
        }
    if not (direct_match or bridge_hit_count):
        return {
            "action": "hold",
            "route_posture": "diagnostic_only",
            "reason_codes": ["path_no_frontier_overlap"],
        }
    if not has_source_signal and not has_route_handle:
        return {
            "action": "abstain",
            "route_posture": "diagnostic_only",
            "reason_codes": ["source_free_path_evaporated"],
        }
    action = "expand" if bridge_hit_count else "deepen"
    return {
        "action": action,
        "route_posture": "reopenable_route",
        "reason_codes": ["path_found_reopenable"],
    }


def walk_associative_paths(
    *,
    query: str,
    candidates: Sequence[Mapping[str, Any]],
    bridge_rows: Iterable[Mapping[str, Any]] | None = None,
    navigation_rows: Iterable[Mapping[str, Any]] | None = None,
    active_locks: Iterable[Mapping[str, Any]] | None = None,
    feedback_rows: Iterable[Mapping[str, Any]] | None = None,
    limit: int = 3,
    max_depth: int = 2,
) -> dict[str, Any]:
    query_terms = _terms(_split_query(query), limit=24)
    distinctive = [term for term in query_terms if not _generic(term)]
    reason_codes: list[str] = []
    if not distinctive:
        return _report(
            decision="abstain",
            query_terms=query_terms,
            candidates=[],
            reason_codes=["path_low_specificity", "path_abstained_tighten_cue"],
            blocked_count=0,
            evaporated_count=0,
            max_depth=max_depth,
        )

    feedback = [row for row in feedback_rows or [] if isinstance(row, Mapping)]
    bridges = reduce_semantic_bridge_candidates(bridge_rows or [], feedback_rows=feedback)
    locks = [row for row in active_locks or [] if isinstance(row, Mapping)]
    navigation = [row for row in navigation_rows or [] if isinstance(row, Mapping)]
    candidate_rows = [row for row in candidates if isinstance(row, Mapping)]
    candidate_rows.extend(_rows_to_candidates(navigation, source="navigation_potential"))
    candidate_rows.extend(_rows_to_candidates(locks, source="active_recall_lock"))

    usable_bridges = []
    blocked_count = 0
    for bridge in bridges:
        status = str(bridge.get("status") or "").casefold()
        if status != "accepted":
            blocked_count += 1
            bridge_reasons = {str(reason) for reason in bridge.get("reason_codes") or []}
            if status in {"blocked", "retired", "demoted", "local_only_scent", "rejected"}:
                reason_codes.append(
                    "source_free_path_evaporated"
                    if "source_free_bridge_cannot_expand_public_query" in bridge_reasons
                    else "path_blocked_private_or_stale"
                )
            continue
        if not _bridge_overlaps(distinctive, bridge):
            continue
        usable_bridges.append(bridge)

    scored: list[dict[str, Any]] = []
    evaporated_count = 0
    feedback_counts = _feedback_counts(feedback)
    feedback_by_id = _feedback_by_id(feedback)
    for row in candidate_rows:
        private_or_stale = _private_or_stale(row)
        private_policy = decide_associative_frontier_step(
            direct_match=False,
            bridge_hit_count=0,
            has_source_signal=False,
            has_route_handle=False,
            private_or_stale=private_or_stale,
        )
        if private_policy["action"] == "block":
            blocked_count += 1
            reason_codes.extend(private_policy["reason_codes"])
            continue
        route_id = _route_id(row)
        negative_feedback = _negative_feedback(route_id, row, feedback_counts)
        negative_policy = decide_associative_frontier_step(
            direct_match=False,
            bridge_hit_count=0,
            has_source_signal=False,
            has_route_handle=False,
            negative_feedback=negative_feedback,
        )
        if negative_policy["action"] == "shadow":
            evaporated_count += 1
            reason_codes.extend(negative_policy["reason_codes"])
            continue
        candidate_terms = _candidate_terms(row)
        direct = _overlap(distinctive, candidate_terms)
        bridge_hits = [
            bridge
            for bridge in usable_bridges
            if _overlap(_bridge_to_terms(bridge), candidate_terms)
        ]
        generic_only = bool(_overlap(query_terms, candidate_terms)) and not direct and not bridge_hits
        refs = _safe_refs(row.get("source_refs")) + _safe_refs(
            [ref for bridge in bridge_hits for ref in bridge.get("source_refs") or []]
        )
        event_refs = _safe_refs(row.get("event_refs")) + _safe_refs(
            [ref for bridge in bridge_hits for ref in bridge.get("event_refs") or []]
        )
        selected_refs = _dedupe_refs(refs or event_refs, limit=4)
        source_ref_digest = apw_route_identity.source_ref_digest(selected_refs)
        frontier = decide_associative_frontier_step(
            direct_match=bool(direct),
            bridge_hit_count=len(bridge_hits),
            has_source_signal=bool(refs or event_refs),
            has_route_handle=_has_route_handle(row),
            generic_only=generic_only,
        )
        if frontier["action"] == "hold":
            continue
        if frontier["action"] == "abstain":
            evaporated_count += 1
            reason_codes.extend(frontier["reason_codes"])
            continue
        positive, ignored_positive = _positive_feedback(route_id, row, feedback_by_id)
        if ignored_positive:
            reason_codes.append("cross_scope_positive_feedback_ignored")
        score = len(direct) * 2.0 + len(bridge_hits) * 2.5 + (1.0 if refs or event_refs else 0.5)
        if positive:
            score += 1.0
        matched_terms = unique_preserve([*direct, *_bridge_to_terms_many(bridge_hits)], limit=8)
        candidate_source_kind = str(
            row.get("candidate_source_kind") or row.get("source") or ""
        )[:80] or None
        scored.append(
            {
                "kind": "aippocampus_associative_path_candidate",
                "schema_version": SCHEMA_VERSION,
                "route_id": route_id,
                "thread_key": str(row.get("thread_key") or "")[:120] or None,
                "candidate_id": str(row.get("candidate_id") or "")[:120] or None,
                "candidate_source_kind": candidate_source_kind,
                "score": round(score, 3),
                "matched_terms": matched_terms,
                "bridge_ids": unique_preserve(
                    [str(bridge.get("candidate_id") or "") for bridge in bridge_hits],
                    limit=4,
                ),
                "source_refs": _dedupe_refs(refs, limit=4),
                "event_refs": _dedupe_refs(event_refs, limit=4),
                "source_ref_digest": source_ref_digest,
                "scope_bucket": _scope_bucket(row),
                "freshness": str(
                    row.get("freshness")
                    or row.get("currentness")
                    or row.get("status")
                    or "current"
                )[:80],
                "visibility": str(row.get("visibility") or "")[:80],
                "source_epoch": row.get("source_epoch"),
                "invalidation_epoch": row.get("invalidation_epoch"),
                "invalidation_reasons": row.get("invalidation_reasons"),
                "source_coverage_time": row.get("source_coverage_time"),
                "source_shape_completeness": row.get("source_shape_completeness") or "complete",
                "authority_level": authority.AUTHORITY_NAVIGATION_ONLY,
                "action_grammar": authority.ACTION_REOPENABLE_ROUTE,
                "claim_permission": authority.CLAIM_NO_CLAIM_BEFORE_REOPEN,
                "source_reopen_required_before_claim": True,
                "claim_boundary": "navigation_only_no_claim_before_reopen",
                "apw_route_identity": apw_route_identity.route_identity_envelope(
                    public_route_id=route_id,
                    apw_candidate_route_id=route_id,
                    apw_candidate_id=row.get("candidate_id"),
                    source_refs=selected_refs,
                    source_ref_digest_value=source_ref_digest,
                    matched_cue_anchors=matched_terms,
                    candidate_source_kind=candidate_source_kind,
                    source_shape_posture="reopenable_route",
                ),
                "reason_codes": unique_preserve(
                    [
                        "path_found_reopenable",
                        *("source_backed_semantic_bridge" for _ in bridge_hits[:1]),
                        *("positive_feedback_same_scope" for _ in [1] if positive),
                    ],
                    limit=5,
                ),
            }
        )

    scored.sort(key=lambda row: (-float(row.get("score") or 0.0), str(row.get("route_id") or "")))
    selected = scored[: max(0, int(limit))]
    if selected:
        return _report(
            decision="route_candidates",
            query_terms=query_terms,
            candidates=selected,
            reason_codes=["path_found_reopenable", *reason_codes],
            blocked_count=blocked_count,
            evaporated_count=evaporated_count,
            max_depth=max_depth,
        )
    if reason_codes:
        reason_codes.append("path_abstained_tighten_cue")
    else:
        reason_codes.extend(["path_abstained_tighten_cue"])
    return _report(
        decision="abstain",
        query_terms=query_terms,
        candidates=[],
        reason_codes=reason_codes,
        blocked_count=blocked_count,
        evaporated_count=evaporated_count,
        max_depth=max_depth,
    )


def _report(
    *,
    decision: str,
    query_terms: list[str],
    candidates: list[dict[str, Any]],
    reason_codes: list[str],
    blocked_count: int,
    evaporated_count: int,
    max_depth: int,
) -> dict[str, Any]:
    distinctive_terms = [term for term in query_terms if not _generic(term)]
    return {
        "kind": "aippocampus_associative_path_walk",
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "frontier_policy": {
            "name": FRONTIER_POLICY_NAME,
            "max_depth": max(1, min(2, int(max_depth or 1))),
            "distinctive_term_count": len(distinctive_terms),
            "expansion_rules": [
                "distinctive_query_term_overlap",
                "accepted_semantic_bridge_overlap",
                "navigation_and_active_lock_candidates_only",
            ],
            "evaporation_rules": [
                "generic_only_path",
                "private_or_stale_path",
                "source_free_path",
                "negative_feedback_path",
            ],
            "feedback_rules": [
                "positive_feedback_lifts_same_safe_scope_only",
                "cross_scope_positive_feedback_is_ignored",
            ],
            "authority": "navigation_only_no_claim_before_reopen",
        },
        "authority_level": authority.AUTHORITY_NAVIGATION_ONLY,
        "claim_permission": authority.CLAIM_NO_CLAIM_BEFORE_REOPEN,
        "action_grammar": (
            authority.ACTION_REOPENABLE_ROUTE if candidates else authority.ACTION_DIRECTION_ONLY
        ),
        "query_term_count": len(query_terms),
        "max_depth": max(1, min(2, int(max_depth or 1))),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "reason_codes": unique_preserve(reason_codes, limit=10),
        "metrics": {
            "blocked_private_or_stale_count": int(blocked_count),
            "evaporated_path_count": int(evaporated_count),
            "source_reopenable_candidate_count": len(candidates),
        },
        "cannot_claim": ["associative_path_as_source_truth"],
    }


def _split_query(query: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff.-]+", str(query or ""), flags=re.UNICODE)


def _terms(values: Iterable[Any], *, limit: int = 16) -> list[str]:
    terms: list[str] = []
    for value in values:
        if isinstance(value, str):
            normalized = normalize_term(value)
            if normalized and len(normalized) <= 96:
                terms.append(normalized)
        elif isinstance(value, Iterable):
            terms.extend(_terms(value, limit=limit))
    return unique_preserve(terms, limit=limit)


def _generic(term: str) -> bool:
    folded = normalize_term(term).casefold()
    if not folded or folded in GENERIC_TERMS:
        return True
    # English one- and two-character tokens are usually noise, but Chinese
    # two-character project cues can be highly distinctive ("黏菌" is the APW
    # dogfood example). Keep one-character CJK tokens filtered.
    if re.fullmatch(r"[\u4e00-\u9fff]{2,}", folded):
        return False
    return len(folded) <= 2


def _candidate_terms(row: Mapping[str, Any]) -> list[str]:
    raw: list[Any] = []
    for key in (
        "title",
        "route_label",
        "route_topic",
        "project_label",
        "keywords",
        "terms",
        "query_terms",
        "route_terms",
        "trigger_terms",
        "anchor_terms",
    ):
        value = row.get(key)
        if isinstance(value, str):
            raw.append(value)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            raw.extend(value)
    return _terms(raw, limit=48)


def _bridge_to_terms(bridge: Mapping[str, Any]) -> list[str]:
    return _terms([*(bridge.get("to_terms") or []), *(bridge.get("route_aliases") or [])], limit=24)


def _bridge_to_terms_many(bridges: Iterable[Mapping[str, Any]]) -> list[str]:
    return unique_preserve([term for bridge in bridges for term in _bridge_to_terms(bridge)], limit=16)


def _bridge_from_terms(bridge: Mapping[str, Any]) -> list[str]:
    return _terms([*(bridge.get("from_terms") or []), *(bridge.get("route_aliases") or [])], limit=24)


def _bridge_overlaps(distinctive: Sequence[str], bridge: Mapping[str, Any]) -> bool:
    return bool(_overlap(distinctive, _bridge_from_terms(bridge)))


def _overlap(left: Sequence[str], right: Sequence[str]) -> list[str]:
    matches: list[str] = []
    right_low = [term.casefold() for term in right]
    for term in left:
        folded = term.casefold()
        if not folded:
            continue
        if any(folded == other or folded in other or other in folded for other in right_low):
            matches.append(term)
    return unique_preserve(matches, limit=12)


def _route_id(row: Mapping[str, Any]) -> str:
    for key in ("route_id", "candidate_id", "thread_key", "id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value[:120]
    return "route:unknown"


def _rows_to_candidates(rows: Iterable[Mapping[str, Any]], *, source: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        clean = dict(row)
        clean.setdefault("route_id", row.get("route_id") or row.get("candidate_id") or row.get("lock_id"))
        clean.setdefault("route_terms", row.get("route_terms") or row.get("terms") or row.get("anchor_terms"))
        clean.setdefault("source", source)
        candidates.append(clean)
    return candidates


def _safe_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = {
            str(key): row.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
                "event_id",
            )
            if row.get(key) not in (None, "", [])
        }
        if clean:
            refs.append(clean)
    return refs


def _dedupe_refs(refs: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        marker = tuple(sorted((key, str(value)) for key, value in ref.items()))
        if marker not in seen:
            seen.add(marker)
            result.append(dict(ref))
        if len(result) >= limit:
            break
    return result


def _has_route_handle(row: Mapping[str, Any]) -> bool:
    return bool(row.get("thread_key") or row.get("route_id") or row.get("candidate_id"))


def _private_or_stale(row: Mapping[str, Any]) -> bool:
    bucket = str(row.get("scope_bucket") or row.get("privacy_partition") or "").casefold()
    status = str(row.get("freshness") or row.get("status") or row.get("currentness") or "").casefold()
    visibility = str(row.get("visibility") or "").casefold()
    return bucket in PRIVATE_BUCKETS or status in STALE_STATUSES or visibility == "blocked"


def _scope_bucket(row: Mapping[str, Any]) -> str:
    for key in ("scope_bucket", "privacy_partition", "privacy_domain", "scope"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return value[:80]
    return DEFAULT_SAFE_SCOPE


def _scope_allows_positive_feedback(candidate: Mapping[str, Any], feedback: Mapping[str, Any]) -> bool:
    # Positive feedback amplifies a navigation route. It must not cross privacy or
    # project boundaries, otherwise a successful private/source-local reopen can
    # silently drag an unrelated foreground agent toward the wrong route.
    candidate_scope = _scope_bucket(candidate)
    feedback_scope = _scope_bucket(feedback)
    if candidate_scope != feedback_scope:
        return False
    if candidate_scope in PRIVATE_BUCKETS or feedback_scope in PRIVATE_BUCKETS:
        return False
    return not _private_or_stale(candidate) and not _private_or_stale(feedback)


def _feedback_signal(row: Mapping[str, Any]) -> str:
    signal = str(row.get("signal") or row.get("outcome") or "").strip()
    if signal == "wrong_route":
        return "wrong_route_drag"
    return signal


def _feedback_keys(row: Mapping[str, Any]) -> set[str]:
    return apw_route_identity.identity_keys(row.get("route_id"), row)


def _candidate_feedback_keys(route_id: str, row: Mapping[str, Any]) -> set[str]:
    return apw_route_identity.identity_keys(route_id, row)


def _feedback_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = {}
    for row in rows:
        signal = _feedback_signal(row)
        if signal:
            for route_id in _feedback_keys(row):
                counts.setdefault(route_id, Counter())[signal] += 1
    return counts


def _feedback_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not _feedback_signal(row):
            continue
        for route_id in _feedback_keys(row):
            by_id.setdefault(route_id, []).append(row)
    return by_id


def _negative_feedback(route_id: str, row: Mapping[str, Any], counts: Mapping[str, Counter[str]]) -> bool:
    keys = _candidate_feedback_keys(route_id, row)
    return any(counts.get(key, Counter()).get(signal, 0) for key in keys for signal in NEGATIVE_OUTCOMES)


def _positive_feedback(
    route_id: str,
    row: Mapping[str, Any],
    by_id: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[bool, bool]:
    matched_positive = [
        feedback
        for key in _candidate_feedback_keys(route_id, row)
        for feedback in by_id.get(key, [])
        if _feedback_signal(feedback) in POSITIVE_OUTCOMES
    ]
    if not matched_positive:
        return False, False
    same_scope = any(_scope_allows_positive_feedback(row, feedback) for feedback in matched_positive)
    return same_scope, not same_scope
