#!/usr/bin/env python3
"""Helpers for familiarity-card avatar illumination."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs

STATE_KIND = "source_backed_avatar_state"
FOREGROUND_KIND = "source_backed_avatar_foreground_packet"
DECISION_SHADOW_KIND = "avatar_decision_shadow_negative_attention"
SCHEMA_VERSION = 1
AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"
ACTION_GRAMMAR_ACTIVE = "reopenable_route"
ACTION_GRAMMAR_SHADOW = "direction_with_ref"
ACTION_GRAMMAR_BLOCKED = "ignore_or_blocked"

ALLOWED_SEMANTIC_INVALIDATION_REASONS: tuple[str, ...] = (
    "user_correction",
    "superseding_decision",
    "topic_epoch_changed",
    "registry_freshness_changed",
    "clean_source_freshness_changed",
    "source_fingerprint_changed",
    "contradiction_visible",
    "review_due",
    "macro_recheck_required",
)

PARTIAL_INVALIDATION_REASONS = {
    "topic_epoch_changed",
    "registry_freshness_changed",
    "clean_source_freshness_changed",
    "review_due",
    "macro_recheck_required",
}
BLOCKED_PRIVACY_STATES = {
    "blocked",
    "private",
    "sensitive",
    "partition_blocked",
    "ignore_or_blocked",
}
STALE_FRESHNESS_STATES = {"stale", "expired", "superseded", "invalidated", "conflicted"}
TASK_FACETS = ("builder", "reviewer", "archivist", "companion")
MACRO_LAYERS = ("earth", "human", "heaven")
TASK_FACET_CUES: dict[str, tuple[str, ...]] = {
    "builder": (
        "build",
        "change",
        "edit",
        "feature",
        "fix",
        "implement",
        "patch",
        "runtime",
        "wire",
        "实现",
        "修改",
    ),
    "reviewer": (
        "acceptance",
        "boundary",
        "check",
        "claim",
        "risk",
        "test",
        "verify",
        "review",
        "验证",
        "审查",
    ),
    "archivist": (
        "history",
        "reopen",
        "source",
        "source_refs",
        "docs",
        "decision",
        "freshness",
        "invalidation",
        "来源",
        "文档",
    ),
    "companion": (
        "tone",
        "relationship",
        "pacing",
        "warmth",
        "companion",
        "care",
        "节奏",
        "关系",
    ),
}
MACRO_LAYER_CUES: dict[str, tuple[str, ...]] = {
    "earth": (
        "artifact",
        "benchmark",
        "code",
        "evidence",
        "file",
        "fixture",
        "implementation",
        "source",
        "test",
        "证据",
        "测试",
    ),
    "human": (
        "action",
        "agent",
        "decision",
        "issue",
        "pr",
        "review",
        "route",
        "task",
        "workflow",
        "行动",
        "任务",
    ),
    "heaven": (
        "direction",
        "north star",
        "positioning",
        "product",
        "purpose",
        "roadmap",
        "strategy",
        "thesis",
        "方向",
        "路线图",
    ),
}


def stable_id(*parts: Any, prefix: str, length: int = 18) -> str:
    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def text(value: Any, limit: int = 180) -> str:
    return compact_text(str(value or "").strip(), limit)


def code(value: Any, *, limit: int = 80) -> str:
    raw = text(value, limit).casefold()
    raw = re.sub(r"[\s\-]+", "_", raw)
    return "".join(ch for ch in raw if ch.isalnum() or ch == "_").strip("_")


def terms(value: Any) -> set[str]:
    raw = str(value or "").casefold()
    return {term for term in re.findall(r"[a-z0-9_]+", raw) if len(term) > 2}


def strings(value: Any, *, limit: int = 8, item_limit: int = 100) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        item_text = text(item, item_limit)
        if not item_text:
            continue
        key = item_text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item_text)
        if len(out) >= limit:
            break
    return out


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def privacy_state(card: Mapping[str, Any]) -> str:
    policy = mapping(card.get("injection_policy"))
    state = (
        card.get("privacy_state")
        or card.get("privacy")
        or card.get("privacy_action")
        or policy.get("privacy_state")
        or policy.get("privacy")
        or ("blocked" if card.get("privacy_blocked") or policy.get("privacy_blocked") else "allowed")
    )
    return code(state) or "allowed"


def freshness_state(card: Mapping[str, Any]) -> str:
    return code(card.get("freshness") or card.get("freshness_state") or "unknown") or "unknown"


def card_terms(card: Mapping[str, Any], *, task: str = "") -> set[str]:
    fields: list[Any] = [
        task,
        card.get("domain"),
        card.get("landmark"),
        card.get("category"),
        card.get("boundary"),
        card.get("why_now"),
        card.get("action_delta_required"),
        card.get("first_source_to_reopen"),
        card.get("stop_after"),
        " ".join(strings(card.get("route_terms"), limit=24)),
        " ".join(strings(card.get("do_not_use_for"), limit=12)),
    ]
    route = mapping(card.get("route"))
    for values in route.values():
        fields.append(" ".join(strings(values, limit=12)))
    shadow = mapping(card.get("decision_shadow"))
    fields.extend(str(value) for value in shadow.values())
    return terms(" ".join(str(field or "") for field in fields))


def task_relevant(card: Mapping[str, Any], task: str) -> bool:
    task_words = terms(task)
    if not task_words:
        return True
    return bool(task_words & card_terms(card))


def source_diversity(refs: Sequence[Mapping[str, Any]]) -> int:
    families: set[str] = set()
    for ref in refs:
        path = text(ref.get("path"), 200)
        kind = text(ref.get("kind"), 80)
        source_id = text(ref.get("source_id"), 120)
        if path:
            families.add(path.split("/")[0].split("\\")[0] or path)
        elif kind:
            families.add(kind)
        elif source_id:
            families.add(source_id.split(":")[0])
    return len(families) or (1 if refs else 0)


def _score_cues(term_set: set[str], cues: Sequence[str]) -> int:
    normalized_cues = {code(cue) for cue in cues}
    return len(term_set & normalized_cues)


def facet_illumination(
    card: Mapping[str, Any],
    task: str,
    refs: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    term_set = card_terms(card, task=task)
    source_density = len(refs)
    diversity = source_diversity(refs)
    scores: dict[str, float] = {}
    for layer in MACRO_LAYERS:
        raw = _score_cues(term_set, MACRO_LAYER_CUES[layer])
        scores[layer] = round(min(1.0, 0.18 + raw * 0.12 + source_density * 0.035 + diversity * 0.04), 3)
    for facet in TASK_FACETS:
        raw = _score_cues(term_set, TASK_FACET_CUES[facet])
        scores[facet] = round(min(1.0, 0.08 + raw * 0.13 + source_density * 0.04 + diversity * 0.035), 3)
    if card.get("first_source_to_reopen"):
        scores["archivist"] = round(min(1.0, scores["archivist"] + 0.16), 3)
    if card.get("stop_after") or card.get("do_not_use_for"):
        scores["reviewer"] = round(min(1.0, scores["reviewer"] + 0.12), 3)
    if card.get("action_delta_required"):
        scores["builder"] = round(min(1.0, scores["builder"] + 0.1), 3)
    return scores


def active_task_facets(
    illumination: Mapping[str, float],
    *,
    narrow_to_facets: Sequence[str] = (),
) -> list[dict[str, Any]]:
    allowed = {code(facet) for facet in narrow_to_facets if code(facet)}
    active: list[dict[str, Any]] = []
    for facet in TASK_FACETS:
        if allowed and facet not in allowed:
            continue
        weight = float(illumination.get(facet) or 0.0)
        if weight >= 0.32 or (allowed and facet in allowed):
            active.append(
                {
                    "facet": facet,
                    "weight": round(max(weight, 0.34 if allowed else weight), 3),
                    "authority_level": AUTHORITY_LEVEL,
                    "claim_permission": CLAIM_PERMISSION,
                }
            )
    if not active and not allowed:
        best = max(TASK_FACETS, key=lambda item: float(illumination.get(item) or 0.0))
        active.append(
            {
                "facet": best,
                "weight": round(float(illumination.get(best) or 0.2), 3),
                "authority_level": AUTHORITY_LEVEL,
                "claim_permission": CLAIM_PERMISSION,
            }
        )
    return active


def posture_tensions(active_facets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    facets = {str(item.get("facet") or "") for item in active_facets}
    tensions: list[dict[str, Any]] = []
    if {"builder", "reviewer"} <= facets:
        tensions.append(
            {
                "tension": "builder_reviewer",
                "posture": "build_narrowly_and_verify_before_claiming",
                "authority_level": AUTHORITY_LEVEL,
            }
        )
    if {"companion", "reviewer"} <= facets:
        tensions.append(
            {
                "tension": "companion_reviewer",
                "posture": "stay_warm_without_relaxing_source_boundaries",
                "authority_level": AUTHORITY_LEVEL,
            }
        )
    return tensions


def semantic_invalidation_state(events: Iterable[Mapping[str, Any]] | None) -> dict[str, Any]:
    """Normalize deterministic source-change signals for card/avatar consumers."""

    reason_codes: list[str] = []
    source_refs: list[dict[str, Any]] = []
    rejected_events: list[dict[str, str]] = []
    first_source = ""
    narrow_to: list[str] = []
    partial = False
    file_fingerprints_still_match = False
    for event in events or []:
        if not isinstance(event, Mapping):
            continue
        reason = code(event.get("reason_code") or event.get("reason"))
        if reason not in ALLOWED_SEMANTIC_INVALIDATION_REASONS:
            rejected_events.append(
                {
                    "reason": "unsupported_reason_code",
                    "reason_code": reason or "missing_reason_code",
                }
            )
            continue
        if reason not in reason_codes:
            reason_codes.append(reason)
        if event.get("partial_invalidation") or reason in PARTIAL_INVALIDATION_REASONS:
            partial = True
        if event.get("file_fingerprints_still_match"):
            file_fingerprints_still_match = True
        if not first_source:
            first_source = text(event.get("first_source_to_reopen"), 220)
        for facet in strings(event.get("narrow_to_facets"), limit=4):
            facet_code = code(facet)
            if facet_code in TASK_FACETS and facet_code not in narrow_to:
                narrow_to.append(facet_code)
        for ref in safe_source_refs(event.get("source_refs")):
            if ref not in source_refs:
                source_refs.append(ref)

    if not first_source and source_refs:
        first = source_refs[0]
        first_source = text(first.get("path") or first.get("source_id") or first.get("thread_key"), 220)
    return {
        "active": bool(reason_codes),
        "reason_codes": reason_codes,
        "rejected_events": rejected_events,
        "partial_invalidation": partial and bool(reason_codes),
        "narrow_to_facets": narrow_to,
        "source_refs": source_refs,
        "first_source_to_reopen": first_source,
        "file_fingerprints_still_match": file_fingerprints_still_match,
        "source_reopen_required_before_use": bool(reason_codes),
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "semantic_invalidation_is_not_truth_adjudication": True,
    }


def card_state(
    card: Mapping[str, Any],
    semantic_state: Mapping[str, Any],
    refs: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str]:
    privacy = privacy_state(card)
    if privacy in BLOCKED_PRIVACY_STATES:
        return "blocked_boundary", "absent", ACTION_GRAMMAR_BLOCKED
    if not refs:
        return "missing_source", "absent", ACTION_GRAMMAR_BLOCKED
    freshness = freshness_state(card)
    if freshness in STALE_FRESHNESS_STATES:
        return "suspect", "shadowed", ACTION_GRAMMAR_SHADOW
    if semantic_state.get("active"):
        if semantic_state.get("partial_invalidation"):
            return "partial_invalidation", "narrowed", ACTION_GRAMMAR_SHADOW
        return "suspect", "shadowed", ACTION_GRAMMAR_SHADOW
    return "valid", "active", ACTION_GRAMMAR_ACTIVE


def activation(
    *,
    active: bool,
    refs: Sequence[Mapping[str, Any]],
    state: str,
    illumination: Mapping[str, float],
) -> dict[str, Any]:
    density = len(refs)
    diversity = source_diversity(refs)
    counter_evidence = 1 if state in {"suspect", "partial_invalidation"} else 0
    strength = min(
        1.0,
        0.25 + density * 0.11 + diversity * 0.08 + max(illumination.values() or [0.0]) * 0.42,
    )
    if state == "partial_invalidation":
        strength = min(strength, 0.58)
    if not active:
        strength = 0.0
    return {
        "active": active,
        "strength": round(strength, 3),
        "source_density": density,
        "source_diversity": diversity,
        "authority_floor": "navigation",
        "freshness": "suspect" if state in {"suspect", "partial_invalidation"} else "current",
        "counter_evidence_count": counter_evidence,
    }


def attention_bias(active_facets: Sequence[Mapping[str, Any]], *, action_grammar: str) -> list[str]:
    biases: list[str] = []
    facets = {str(item.get("facet") or "") for item in active_facets}
    if "builder" in facets:
        biases.append("small_patch_shape")
    if "reviewer" in facets:
        biases.append("focused_verification")
    if "archivist" in facets or action_grammar != ACTION_GRAMMAR_ACTIVE:
        biases.append("source_reopen_first")
    if "companion" in facets:
        biases.append("tone_and_pacing")
    return biases[:4] or ["source_reopen_first"]


def posture_line(active_facets: Sequence[Mapping[str, Any]], *, lifecycle_state: str) -> str:
    facets = {str(item.get("facet") or "") for item in active_facets}
    if lifecycle_state == "narrowed":
        return "use only the narrowed posture, then reopen source before widening scope"
    if {"builder", "reviewer"} <= facets:
        return "build narrowly, verify the changed surface, and preserve claim boundaries"
    if "archivist" in facets:
        return "reopen the cited source trail before using the route shape"
    if "reviewer" in facets:
        return "check boundary and evidence before acting"
    if "builder" in facets:
        return "take the smallest source-backed next step"
    return "stay source-backed and quiet unless the route changes the next action"


def decision_shadow_action(shadow: Mapping[str, Any]) -> str:
    raw = " ".join(str(shadow.get(key) or "") for key in ("status", "route_constraint", "constraint", "outcome"))
    normalized = raw.casefold()
    if "do_not_repeat" in normalized or "rejected_route" in normalized or "rejected route" in normalized:
        return "avoid"
    if "ask" in normalized:
        return "ask_before"
    if "reopen" in normalized:
        return "reopen_first"
    return "review_before"


def guidance_text(action: str) -> str:
    if action == "avoid":
        return "avoid repeating the old route until the cited source is reopened"
    if action == "ask_before":
        return "ask before reviving the old route unless source has been reopened"
    if action == "reopen_first":
        return "reopen the cited source before using the route"
    return "review the cited source before repeating this path"
