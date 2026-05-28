#!/usr/bin/env python3
"""Scout taxonomy and output-profile contracts for warm ambient recall.

This module is deliberately static: it defines the scout lanes, their task
profiles, and the lens text sent to model scouts. Keep runtime orchestration,
source validation, and cache writes outside this file so profile tuning cannot
quietly change execution semantics.
"""

from __future__ import annotations

from typing import Any

from ambient_recall_cards import (
    ACTIVE_GENTLE_NUDGE,
    CANDIDATE,
    DEEP_ARCHIVAL_RECALL,
    EVIDENCE,
    SCENT,
    SILENT_TUNING,
    SOURCE_BACKED_RECALL_CARD,
)

SCOUT_FAMILIES = (
    "intent_mode_classifier",
    "privacy_boundary_guard",
    "deep_theme_matcher",
    "key_line_hunter",
    "evidence_gap_sentinel",
    "user_style_preference",
    "trajectory_matcher",
    "cross_domain_bridge",
    "nudge_writer",
    "semantic_expander",
)

SCOUT_VARIANTS = (
    "direct",
    "registry_window",
    "clean_source_window",
    "current_trace_window",
    "skeptic_window",
)

# Launch lanes variant-major so quorum-first runs see different functional
# families before they see five variants of the same classifier. This preserves
# the 10x5 taxonomy while letting Flash spend early latency on recall diversity:
# intent/guard/theme/key-line/evidence arrive together, instead of classifier
# aliases satisfying quorum before any card-producing scout runs.
DEFAULT_SCOUTS = tuple(
    f"{family}:{variant}" for variant in SCOUT_VARIANTS for family in SCOUT_FAMILIES
)

SCOUT_PRIORITY = {
    "intent_mode_classifier": "P0",
    "privacy_boundary_guard": "P0",
    "deep_theme_matcher": "P0",
    "key_line_hunter": "P0",
    "evidence_gap_sentinel": "P0",
    "user_style_preference": "P1",
    "trajectory_matcher": "P1",
    "cross_domain_bridge": "P1",
    "nudge_writer": "P1",
    "semantic_expander": "P1",
}

LEGACY_SCOUT_ALIASES = {
    "query_expansion": "semantic_expander",
    "life_wide_cue_classifier": "intent_mode_classifier",
    "thread_matcher": "trajectory_matcher",
    "current_thread_filter": "evidence_gap_sentinel",
    "theme_matcher": "deep_theme_matcher",
    "evidence_judge": "evidence_gap_sentinel",
    "privacy_scope_guard": "privacy_boundary_guard",
    "failure_sentinel": "evidence_gap_sentinel",
}

VALID_DECISIONS = {"skip", "background_only", "scent", "candidate", "evidence"}
VALID_SUPPORT_LEVELS = {SCENT, CANDIDATE, EVIDENCE}
VALID_TOPIC_EPOCH_ACTIONS = {"reuse", "rotate", "suppress"}
VALID_VISIBILITIES = {SILENT_TUNING, ACTIVE_GENTLE_NUDGE, SOURCE_BACKED_RECALL_CARD, DEEP_ARCHIVAL_RECALL}
SUPPORT_RANK = {SCENT: 1, CANDIDATE: 2, EVIDENCE: 3}
SCOUT_CANDIDATE_LIMITS = {
    "intent_mode_classifier": 0,
    "privacy_boundary_guard": 0,
    "evidence_gap_sentinel": 1,
    "deep_theme_matcher": 2,
    "key_line_hunter": 2,
    "user_style_preference": 1,
    "trajectory_matcher": 1,
    "cross_domain_bridge": 2,
    "nudge_writer": 1,
    "semantic_expander": 0,
}

TOPIC_EPOCH_FAMILIES = {
    "intent_mode_classifier",
    "deep_theme_matcher",
    "evidence_gap_sentinel",
    "trajectory_matcher",
}

SCOUT_OUTPUT_PROFILES = {
    "intent_mode_classifier": {
        "allowed_fields": [
            "decision",
            "confidence",
            "topic_epoch_action",
            "topic_epoch_label",
            "topic_epoch_reason",
        ],
        "candidate_fields": [],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 0,
    },
    "privacy_boundary_guard": {
        "allowed_fields": ["decision", "confidence", "block", "negative_contexts", "reason"],
        "candidate_fields": [],
        "query_alias_limit": 0,
        "negative_context_limit": 2,
        "theme_limit": 0,
    },
    "semantic_expander": {
        "allowed_fields": ["decision", "confidence", "query_aliases"],
        "candidate_fields": [],
        "query_alias_limit": 5,
        "negative_context_limit": 0,
        "theme_limit": 0,
    },
    "deep_theme_matcher": {
        "allowed_fields": [
            "decision",
            "confidence",
            "themes",
            "candidates",
            "topic_epoch_action",
            "topic_epoch_label",
            "topic_epoch_reason",
        ],
        "candidate_fields": ["theme", "support_level", "matched_terms", "source_refs", "key_line"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 2,
    },
    "key_line_hunter": {
        "allowed_fields": ["decision", "confidence", "themes", "candidates"],
        "candidate_fields": ["theme", "support_level", "key_line", "matched_terms", "source_refs"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 1,
    },
    "evidence_gap_sentinel": {
        "allowed_fields": [
            "decision",
            "confidence",
            "block",
            "negative_contexts",
            "reason",
            "topic_epoch_action",
            "topic_epoch_label",
            "topic_epoch_reason",
        ],
        "candidate_fields": [],
        "query_alias_limit": 0,
        "negative_context_limit": 2,
        "theme_limit": 0,
    },
    "user_style_preference": {
        "allowed_fields": ["decision", "confidence", "themes", "candidates"],
        "candidate_fields": ["theme", "support_level", "matched_terms", "source_refs"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 1,
    },
    "trajectory_matcher": {
        "allowed_fields": [
            "decision",
            "confidence",
            "themes",
            "candidates",
            "topic_epoch_action",
            "topic_epoch_label",
            "topic_epoch_reason",
        ],
        "candidate_fields": ["theme", "support_level", "matched_terms", "source_refs"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 1,
    },
    "cross_domain_bridge": {
        "allowed_fields": ["decision", "confidence", "themes", "candidates"],
        "candidate_fields": ["theme", "support_level", "matched_terms", "source_refs", "nudge"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 1,
    },
    "nudge_writer": {
        "allowed_fields": ["decision", "confidence", "candidates"],
        "candidate_fields": ["theme", "support_level", "nudge", "matched_terms", "source_refs"],
        "query_alias_limit": 0,
        "negative_context_limit": 0,
        "theme_limit": 0,
    },
}

FAMILY_TASKS = {
    "intent_mode_classifier": "Classify task mode, visibility bias, collaboration posture, and cognitive load.",
    "privacy_boundary_guard": "Suppress credential leaks, personal/financial/relationship material, professional secrets, and over-personalized associations.",
    "deep_theme_matcher": "Match long-running themes, philosophical motives, emotional resonance, and recurring trade-offs.",
    "key_line_hunter": "Find memorable lines, visual images, metaphors, strong assertions, and unresolved questions.",
    "evidence_gap_sentinel": "Check source-ref support, hallucinated refs, missing premises, drift, single-source fragility, and timeliness gaps.",
    "user_style_preference": "Detect source-backed user expression habits, language preferences, pacing, and thinking style.",
    "trajectory_matcher": "Locate the current turn in project, life, or thread trajectory when source sidecars support it.",
    "cross_domain_bridge": "Map technical issues to non-technical ideas, and non-technical ideas back to concrete work.",
    "nudge_writer": "Draft one or two quiet private nudges for the foreground agent to adapt.",
    "semantic_expander": "Generate multilingual, metaphor, and query aliases for cold path and next-turn recall.",
}

VARIANT_TASKS = {
    "direct": "Use the direct sanitized prompt and its most literal cues.",
    "registry_window": "Focus on registry titles, summaries, anchors, and project labels.",
    "clean_source_window": "Focus on source-ref-backed candidate windows and exact support.",
    "current_trace_window": "Focus on recent sanitized prompt trace and detect current-thread echo.",
    "skeptic_window": "Act as a skeptical validator; prefer suppress, downgrade, or no-op when weak.",
}

FAMILY_LENS_TASKS = {
    "intent_mode_classifier": "Classify task type, collaboration posture, timeline, flow focus, and cognitive load.",
    "privacy_boundary_guard": "Guard privacy and boundaries before any recall card becomes visible.",
    "deep_theme_matcher": "Compare philosophical, product, emotional, obsession-level, and trade-off themes.",
    "key_line_hunter": "Hunt for compact key lines that can anchor useful recall.",
    "evidence_gap_sentinel": "Apply closed-book source-ref validation and gap detection.",
    "user_style_preference": "Infer only source-backed expression habits and user preferences.",
    "trajectory_matcher": "Match current position in project/thread/life trajectory from available sidecars.",
    "cross_domain_bridge": "Bridge technical and non-technical domains without upgrading unsupported resonance.",
    "nudge_writer": "Draft quiet private guidance only after the card is useful; keep wording tentative unless evidence-backed.",
    "semantic_expander": "Find query aliases, metaphors, and multilingual variants for next-turn/cold-path use.",
}

VARIANT_LENS_TASKS = {
    "direct": "Use the direct prompt terms first; keep aliases close to the user's wording.",
    "registry_window": "Use registry anchor titles, summaries, keywords, and project labels as the anchor surface.",
    "clean_source_window": "Use source-ref-backed windows and support terms; do not elevate evidence without dereferenceable refs.",
    "current_trace_window": "Use the sanitized recent trace to find drift and echo; penalize matches that only repeat this thread.",
    "skeptic_window": "Search for reasons to suppress, rotate topic epoch, or downgrade support when the association is weak.",
}

FAMILY_VARIANT_LENS_TASKS = {
    ("intent_mode_classifier", "direct"): "Task type lens: coding, writing, philosophy, planning, repair, logistics, or reflection.",
    ("intent_mode_classifier", "registry_window"): "Flow-focus lens: whether the turn wants fast execution, careful research, design thinking, or quiet support.",
    ("intent_mode_classifier", "clean_source_window"): "Timeline lens: planning, implementation, debugging, calibration, cleanup, or handoff.",
    ("intent_mode_classifier", "current_trace_window"): "Collaboration posture lens: asking, approving, correcting, steering, or asking the agent to continue.",
    ("intent_mode_classifier", "skeptic_window"): "Cognitive-load lens: suppress verbose recall when the user is in a high-load execution moment.",
    ("privacy_boundary_guard", "direct"): "Credential leak lens: block tokens, cookies, connection strings, private paths, and auth-like material.",
    ("privacy_boundary_guard", "registry_window"): "Personal-health lens: downgrade health, body, medical, or intimate wellbeing associations unless explicitly requested.",
    ("privacy_boundary_guard", "clean_source_window"): "Financial lens: suppress private finances, contracts, invoices, accounts, or purchase-sensitive material.",
    ("privacy_boundary_guard", "current_trace_window"): "Relationship privacy lens: suppress family, romantic, friendship, or interpersonal conflict unless directly in scope.",
    ("privacy_boundary_guard", "skeptic_window"): "Professional secret and over-personalization lens: suppress confidential work details and unsolicited intimacy.",
    ("deep_theme_matcher", "direct"): "Philosophical abstraction lens: look for the underlying question or worldview pattern.",
    ("deep_theme_matcher", "registry_window"): "Product-specific lens: match concrete project/product decisions and long-running implementation themes.",
    ("deep_theme_matcher", "clean_source_window"): "Emotional resonance lens: detect repeated felt stakes without treating resonance as fact.",
    ("deep_theme_matcher", "current_trace_window"): "Long-term obsession lens: match durable motifs that recur across prompts and threads.",
    ("deep_theme_matcher", "skeptic_window"): "Contradiction and trade-off lens: prefer candidates that clarify a real tension, not generic similarity.",
    ("key_line_hunter", "direct"): "Visual image lens: find a concrete image or scene-like phrasing that can anchor memory.",
    ("key_line_hunter", "registry_window"): "Structural metaphor lens: find metaphors, names, or frames that organize the work.",
    ("key_line_hunter", "clean_source_window"): "Chinese-English mixing lens: preserve bilingual phrasing when the source used it.",
    ("key_line_hunter", "current_trace_window"): "Strong assertion lens: find compact, emotionally forceful lines worth recalling quietly.",
    ("key_line_hunter", "skeptic_window"): "Unanswered mystery lens: find old unresolved questions without pretending they were answered.",
    ("evidence_gap_sentinel", "direct"): "Hallucinated-ref lens: downgrade source_refs that are absent from shared context or malformed.",
    ("evidence_gap_sentinel", "registry_window"): "Single-source fragility lens: keep solitary weak hits provisional until corroborated.",
    ("evidence_gap_sentinel", "clean_source_window"): "Context-drift lens: verify the cited source supports the present hypothesis, not only a shared term.",
    ("evidence_gap_sentinel", "current_trace_window"): "Missing-premise lens: flag leaps where the current prompt lacks the prerequisite context.",
    ("evidence_gap_sentinel", "skeptic_window"): "Timeliness lens: mark potentially stale decisions, prices, people, rules, or project state as needing fresh checks.",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def scout_lane_parts(scout: str) -> tuple[str, str]:
    raw = str(scout or "").strip()
    if ":" in raw:
        family, variant = raw.split(":", 1)
    else:
        family, variant = raw, "direct"
    family = LEGACY_SCOUT_ALIASES.get(family, family)
    if family not in SCOUT_FAMILIES:
        return "", ""
    if variant not in SCOUT_VARIANTS:
        variant = "direct"
    return family, variant


def expand_scout_lanes(scouts: tuple[str, ...]) -> tuple[str, ...]:
    lanes: list[str] = []
    for scout in scouts:
        family, variant = scout_lane_parts(scout)
        if not family:
            continue
        lane = f"{family}:{variant}"
        if lane not in lanes:
            lanes.append(lane)
    return tuple(lanes)


def lens_task_for(family: str, variant: str) -> str:
    specific = FAMILY_VARIANT_LENS_TASKS.get((family, variant))
    if specific:
        return specific
    family_task = FAMILY_LENS_TASKS.get(family, "Analyze warm ambient recall relevance.")
    variant_task = VARIANT_LENS_TASKS.get(variant, "Use this candidate/query variant carefully.")
    return f"{family_task} {variant_task}"


def output_profile_for_family(family: str) -> dict[str, Any]:
    profile = SCOUT_OUTPUT_PROFILES.get(family) or {}
    max_candidates = SCOUT_CANDIDATE_LIMITS.get(family, 1)
    return {
        "allowed_fields": profile.get("allowed_fields") or ["decision", "confidence"],
        "candidate_fields": profile.get("candidate_fields") or [],
        "max_candidates": max_candidates,
        "max_query_aliases": _safe_int(profile.get("query_alias_limit")),
        "max_themes": _safe_int(profile.get("theme_limit")),
        "max_negative_contexts": _safe_int(profile.get("negative_context_limit")),
    }
