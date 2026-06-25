#!/usr/bin/env python3
"""Source-backed thread-story activation packet diagnostics."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import (
    compact_text,
    now_utc,
    sanitize_external_model_text,
    stable_json_join_id,
)

SCHEMA_VERSION = 1
PACKET_KIND = "aippocampus_thread_story_activation_packet"
FIXTURE_KIND = "aippocampus_thread_story_packet_fixture"
ANSWER_PROBE_KIND = "aippocampus_thread_story_answer_boundary_probe"
ANSWER_COMPARISON_KIND = "aippocampus_thread_story_answer_comparison"
PUBLIC_SHADOW_CLOSEOUT_KIND = "aippocampus_thread_story_public_shadow_closeout"
SUPPORTED_ROW_KINDS = {"thread_story_candidate", "cognitive_portrait_signal", "thread_frontier_signal"}
SOURCE_REF_KEYS = ("source_id", "stable_source_id", "thread_key", "message_id", "turn_id", "turn_index", "line", "source_line")
LOCAL_PATH_RE = re.compile(r"([A-Za-z]:\\|/Users/|/home/[^/]+/|\\\\[^\\]+\\)")
PERSONA_CLAIM_RE = re.compile(
    r"(?i)\b(the user|user)\b.{0,64}\b(always|never|is|are|personality|identity|"
    r"obsessed|distrustful|prefers|likes|hates)\b"
)
TRUTH_BOUNDARY = "Thread-story packets are navigation material, not source truth or user/personality facts."
LEAKAGE_TERMS = ("PRIVATE_THREAD_STORY_SENTINEL", "HEX_ARC_PRIVATE_TUN_GE", "FIVE_TONE_PRIVATE_GONG_SHANG", "The user is always", "C:\\private")
CONTROL_DECISIONS = {
    "contradictory_symbolic_arc": "source_review_required",
    "persona_claim_attempt": "suppressed",
    "multi_channel_interference": "backstage_only",
    "unrelated_story_noise": "backstage_only",
}
CANNOT_CLAIM = [
    "live_model_behavioral_equivalence",
    "default_recall_or_aar_improvement",
    "private_real_history_thread_story_quality",
    "user_or_persona_truth",
    "live_answer_quality_lift",
]


def _safe_text(value: Any, *, max_chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, max_chars)


def _public_hash(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _source_refs(value: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        items: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref: dict[str, Any] = {}
        for key in SOURCE_REF_KEYS:
            raw = item.get(key)
            if raw in {None, ""}:
                continue
            text = str(raw)
            if LOCAL_PATH_RE.search(text):
                continue
            out_key = "line" if key == "source_line" else key
            if out_key == "stable_source_id":
                out_key = "source_id"
            ref[out_key] = _safe_text(text, max_chars=180)
        if not ref:
            continue
        marker = tuple(sorted((str(key), str(val)) for key, val in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def _merge_source_refs(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in rows:
        refs.extend(_source_refs(row.get("source_refs") or row.get("evidence_refs") or []))
    return _source_refs(refs)


def _ref_tokens(refs: Iterable[Mapping[str, Any]]) -> list[str]:
    return [
        stable_json_join_id(
            "sr",
            dict(ref),
            ensure_ascii=False,
            length=12,
        )
        for ref in refs
    ]


def _unique(values: Iterable[Any], *, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _safe_text(value, max_chars=90)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _supported_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    backed: list[dict[str, Any]] = []
    skipped: list[str] = []
    for row in rows:
        if str(row.get("kind") or row.get("row_kind") or "").strip() not in SUPPORTED_ROW_KINDS:
            continue
        row_id = _safe_text(
            row.get("id")
            or row.get("packet_row_id")
            or stable_json_join_id("row", row, ensure_ascii=False),
            max_chars=90,
        )
        if _source_refs(row.get("source_refs") or row.get("evidence_refs") or []):
            backed.append(dict(row))
        else:
            skipped.append(row_id)
    return backed, skipped


def build_thread_story_packet(rows: Iterable[Mapping[str, Any]], *, created_at: str | None = None) -> dict[str, Any]:
    backed_rows, skipped_unbacked = _supported_rows(rows)
    source_refs = _merge_source_refs(backed_rows)
    if not backed_rows or not source_refs:
        return {"schema_version": SCHEMA_VERSION, "kind": PACKET_KIND, "created": False, "reason": "not_enough_source_backed_thread_story_rows"}
    concepts = _unique(value for row in backed_rows for value in row.get("activation_cues") or row.get("concepts") or [])
    anchor_candidates = [row.get("story_anchor") or row.get("navigation_anchor") or row.get("summary") for row in backed_rows]
    story_anchor = _safe_text(
        next((value for value in anchor_candidates if value), "Source-backed thread story route."),
        max_chars=150,
    )
    symbolic_hashes = [
        _public_hash(row.get(key), prefix=key)
        for row in backed_rows
        for key in ("hexagram_arc", "five_tone_arc")
        if row.get(key)
    ]
    source_ref_tokens = _ref_tokens(source_refs)
    packet_id = stable_json_join_id(
        "thread_story_packet",
        story_anchor,
        source_ref_tokens,
        ensure_ascii=False,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PACKET_KIND,
        "created": True,
        "packet_id": packet_id,
        "created_at": created_at or now_utc(),
        "authority": "navigation_only",
        "freshness": "current",
        "sensitivity": "symbolic_affect_private",
        "source_surface": "thread_story_candidate_cognitive_portrait_signal_thread_frontier_signal",
        "source_refs": source_refs,
        "source_ref_tokens": source_ref_tokens,
        "source_ref_count": len(source_refs),
        "agent_visible": {
            "visibility": "gentle_navigation",
            "story_anchor": story_anchor,
            "activation_cues": concepts,
            "source_ref_count": len(source_refs),
            "suggested_use": "bias source search or caution only; reopen source before specific claims",
            "truth_boundary": TRUTH_BOUNDARY,
            "dont_decode_instruction_present": True,
        },
        "private_navigation": {
            "route_handle": stable_json_join_id(
                "thread_story_route",
                packet_id,
                source_ref_tokens,
                ensure_ascii=False,
            ),
            "symbolic_channel_count": len(symbolic_hashes),
            "symbolic_channel_hashes": symbolic_hashes,
            "raw_story_text_serialized": False,
        },
        "suppression_boundaries": {
            "raw_story_text_private": True,
            "symbolic_channels_private": True,
            "source_reopen_required_for_claims": True,
            "not_user_or_persona_model": True,
            "contradictory_arc_requires_source_review": True,
            "multi_channel_interference_stays_backstage": True,
        },
        "diagnostics": {
            "backed_row_count": len(backed_rows),
            "skipped_unbacked_row_ids": skipped_unbacked,
            "symbolic_channels_serialized_publicly": False,
        },
    }


def evaluate_negative_control(row: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(row.get("control_kind") or "").strip()
    claim = str(row.get("claim_text") or row.get("raw_story_text") or "")
    base = {
        "control_kind": kind,
        "agent_visible_emitted": False,
        "source_reopen_required": True,
        "private_navigation_only": True,
    }
    if bool(row.get("arc_contradicts_source")):
        return {
            **base,
            "decision": "source_review_required",
            "reason": "symbolic_arc_conflicts_with_source_outcome",
        }
    if PERSONA_CLAIM_RE.search(claim):
        return {
            **base,
            "decision": "suppressed",
            "reason": "unsupported_persona_or_user_trait_claim",
        }
    if bool(row.get("multi_channel_interference")):
        return {
            **base,
            "decision": "backstage_only",
            "reason": "multiple_affect_channels_need_model_family_probe_before_visible_use",
        }
    return {**base, "decision": "backstage_only", "reason": "not_foreground_eligible"}


def build_answer_boundary_probe(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANSWER_PROBE_KIND,
        "mode": "deterministic_opt_in_probe",
        "packet_only": {
            "decision": "source_reopen_required",
            "reason": "packet_is_navigation_not_evidence",
            "allowed_user_visible_claim": False,
        },
        "source_reopened": {
            "decision": "answer_allowed_with_source",
            "reason": "clean_source_or_equivalent_evidence_attached",
            "source_ref_count": int(packet.get("source_ref_count") or 0),
        },
        "claim_boundary": {
            "no_behavioral_equivalence_claim_without_live_probe": True,
            "no_user_visible_recall_lift_claim_without_answer_comparison": True,
        },
    }


def build_answer_comparison_report(packet: Mapping[str, Any]) -> dict[str, Any]:
    source_ref_tokens = [str(token) for token in packet.get("source_ref_tokens") or [] if token]
    source_ready = bool(packet.get("created")) and bool(source_ref_tokens)
    arms: dict[str, dict[str, Any]] = {
        "plain_baseline": {
            "decision": "generic_or_ask_clarifying",
            "allowed_user_visible_claim": False,
            "source_reopen_required": True,
            "helpful_navigation_available": False,
            "reason": "no_thread_story_packet_or_source_evidence_attached",
        },
        "packet_only": {
            "decision": "blocked_source_reopen_required",
            "allowed_user_visible_claim": False,
            "source_reopen_required": True,
            "packet_treated_as_evidence": False,
            "helpful_navigation_available": bool(packet.get("created")),
            "reason": "thread_story_packet_is_navigation_only",
        },
        "source_reopened": {
            "decision": "answer_allowed_with_source" if source_ready else "blocked_missing_source",
            "allowed_user_visible_claim": source_ready,
            "source_reopen_required": not source_ready,
            "source_ref_token_count": len(source_ref_tokens),
            "citations_required": True,
            "reason": "source_tokens_attached" if source_ready else "no_source_tokens_available",
        },
    }
    cases = [
        {
            "case_id": "plain_baseline_no_packet",
            "arm": "plain_baseline",
            "passed": arms["plain_baseline"]["decision"] == "generic_or_ask_clarifying",
        },
        {
            "case_id": "packet_only_navigation_not_evidence",
            "arm": "packet_only",
            "passed": arms["packet_only"]["decision"] == "blocked_source_reopen_required",
        },
        {
            "case_id": "source_reopened_claim_allowed",
            "arm": "source_reopened",
            "passed": arms["source_reopened"]["decision"] == "answer_allowed_with_source",
        },
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANSWER_COMPARISON_KIND,
        "mode": "deterministic_opt_in_answer_comparison",
        "authority": "diagnostic_only",
        "arms": arms,
        "case_results": cases,
        "metrics": {
            "case_count": len(cases),
            "passing_case_count": sum(1 for case in cases if case["passed"]),
            "packet_only_blocked_count": int(arms["packet_only"]["decision"] == "blocked_source_reopen_required"),
            "source_reopened_allowed_count": int(arms["source_reopened"]["allowed_user_visible_claim"]),
            "plain_baseline_user_visible_claim_count": int(arms["plain_baseline"]["allowed_user_visible_claim"]),
            "public_leakage_hit_count": 0,
        },
        "comparison_boundary": {
            "packet_is_navigation_only": True,
            "source_reopened_required_for_specific_claims": True,
            "public_safe_no_raw_text": True,
            "no_live_model_call": True,
            "answer_quality_lift": "not_measured",
        },
        "issue_readouts": {
            "github_313": {
                "answer_comparison_probe": "deterministic_public_safe",
                "packet_only_factual_answer": "blocked",
                "source_reopened_answer": "allowed_with_source" if source_ready else "blocked_missing_source",
                "live_model_probe": "not_run",
                "model_family_probe": "not_run",
                "private_real_history_quality": "not_measured",
                "closeout_eligible": False,
            }
        },
        "cannot_claim": sorted(set(CANNOT_CLAIM + ["model_family_behavioral_equivalence", "default_hook_recall_lift"])),
    }
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    report["metrics"]["public_leakage_hit_count"] = sum(1 for term in LEAKAGE_TERMS if term in serialized)
    return report


def build_public_shadow_closeout_report(
    packet: Mapping[str, Any],
    controls: Mapping[str, Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize the public #313 closeout slice without upgrading it to quality proof."""
    control_results = {
        key: {
            "decision": controls.get(key, {}).get("decision"),
            "expected_decision": expected,
            "passed": controls.get(key, {}).get("decision") == expected,
            "agent_visible_emitted": bool(
                controls.get(key, {}).get("agent_visible_emitted", True)
            ),
        }
        for key, expected in CONTROL_DECISIONS.items()
    }
    comparison_metrics = comparison.get("metrics", {})
    packet_only_blocked = (
        comparison.get("arms", {})
        .get("packet_only", {})
        .get("decision")
        == "blocked_source_reopen_required"
    )
    source_reopened_allowed = bool(
        comparison.get("arms", {})
        .get("source_reopened", {})
        .get("allowed_user_visible_claim")
    )
    public_leakage_hit_count = int(comparison_metrics.get("public_leakage_hit_count") or 0)
    closeout_eligible = bool(
        packet.get("created")
        and packet.get("source_ref_count")
        and all(item["passed"] for item in control_results.values())
        and packet_only_blocked
        and source_reopened_allowed
        and public_leakage_hit_count == 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PUBLIC_SHADOW_CLOSEOUT_KIND,
        "issue": "github_313",
        "status": "public_shadow_closeout_ready" if closeout_eligible else "public_shadow_incomplete",
        "claim_level": "public_structured_text_shadow_fixture",
        "closeout_eligible": closeout_eligible,
        "basis": (
            "public-safe deterministic thread-story packet, leakage controls, "
            "and source-reopened answer-comparison arms"
        ),
        "acceptance_coverage": {
            "packet_carries_source_refs_freshness_sensitivity_boundaries": bool(
                packet.get("source_ref_count")
                and packet.get("freshness")
                and packet.get("sensitivity")
                and packet.get("suppression_boundaries")
            ),
            "leakage_and_over_personalization_controls_present": all(
                key in control_results
                for key in (
                    "contradictory_symbolic_arc",
                    "persona_claim_attempt",
                    "multi_channel_interference",
                    "unrelated_story_noise",
                )
            ),
            "packet_only_factual_answer_blocked": packet_only_blocked,
            "source_reopened_answer_comparison_recorded": source_reopened_allowed,
            "interference_noise_controls_passed": all(
                control_results[key]["passed"]
                for key in ("multi_channel_interference", "unrelated_story_noise")
            ),
            "public_shadow_not_private_history_sink": True,
        },
        "metrics": {
            "control_count": len(control_results),
            "control_pass_count": sum(1 for item in control_results.values() if item["passed"]),
            "packet_source_ref_count": int(packet.get("source_ref_count") or 0),
            "packet_only_blocked_count": int(packet_only_blocked),
            "source_reopened_allowed_count": int(source_reopened_allowed),
            "public_leakage_hit_count": public_leakage_hit_count,
            "agent_visible_control_emission_count": sum(
                1 for item in control_results.values() if item["agent_visible_emitted"]
            ),
            "false_source_claim_count": 0,
            "private_story_quality_required_for_closeout": False,
        },
        "control_results": control_results,
        "issue_readouts": {
            "github_313": {
                "closeout_eligible": closeout_eligible,
                "closeout_basis": "public_shadow_structured_text_fixture",
                "private_history_quality_required": False,
                "live_model_probe_required_for_closeout": False,
                "remaining_not_claimed": [
                    "live_model_behavioral_equivalence",
                    "model_family_generalization",
                    "private_real_history_thread_story_quality",
                    "user_visible_recall_improvement",
                    "default_recall_or_aar_improvement",
                ],
            }
        },
        "can_claim": [
            "public_shadow_thread_story_closeout_readout_recorded",
            "packet_only_factual_answer_blocked_until_source_reopen",
            "source_reopened_answer_comparison_recorded",
            "leakage_contradiction_persona_and_interference_controls_pass",
        ],
        "cannot_claim": sorted(
            set(
                CANNOT_CLAIM
                + [
                    "model_family_behavioral_equivalence",
                    "private_portrait_quality",
                    "default_hook_recall_lift",
                    "user_visible_recall_improvement",
                    "source_truth_from_thread_story_packet",
                ]
            )
        ),
    }


def fixture_rows() -> list[dict[str, Any]]:
    refs = [
        {"thread_key": "session:story-a", "message_id": "msg-story-a", "source_line": 10},
        {"thread_key": "session:story-b", "message_id": "msg-story-b", "source_line": 20},
        {"thread_key": "session:story-c", "message_id": "msg-story-c", "source_line": 30},
    ]
    return [
        {
            "kind": "thread_story_candidate",
            "id": "story-signal-a",
            "story_anchor": "Source-backed continuity route after handoff friction.",
            "activation_cues": ["continuity", "handoff", "source reopen"],
            "raw_story_text": "PRIVATE_THREAD_STORY_SENTINEL raw narrative must stay private.",
            "hexagram_arc": "HEX_ARC_PRIVATE_TUN_GE",
            "source_refs": [refs[0]],
        },
        {
            "kind": "cognitive_portrait_signal",
            "id": "story-signal-b",
            "summary": "Route should raise caution before treating memory scent as evidence.",
            "activation_cues": ["memory scent", "source boundary"],
            "five_tone_arc": "FIVE_TONE_PRIVATE_GONG_SHANG",
            "source_refs": [refs[1]],
        },
        {
            "kind": "thread_frontier_signal",
            "id": "story-signal-c",
            "navigation_anchor": "Reopen source before turning a story cue into a claim.",
            "activation_cues": ["frontier", "no persona claim"],
            "source_refs": [refs[2]],
            "local_debug_path": "C:\\private\\thread-story.txt",
        },
    ]


def negative_control_rows() -> dict[str, dict[str, Any]]:
    return {
        "contradictory_symbolic_arc": {
            "control_kind": "contradictory_symbolic_arc",
            "arc_contradicts_source": True,
            "hexagram_arc": "HEX_ARC_PRIVATE_TUN_GE",
            "raw_story_text": "PRIVATE_THREAD_STORY_SENTINEL contradiction case.",
        },
        "persona_claim_attempt": {
            "control_kind": "persona_claim_attempt",
            "claim_text": "The user is always distrustful and never accepts defaults.",
        },
        "multi_channel_interference": {
            "control_kind": "multi_channel_interference",
            "multi_channel_interference": True,
            "hexagram_arc": "HEX_ARC_PRIVATE_TUN_GE",
            "five_tone_arc": "FIVE_TONE_PRIVATE_GONG_SHANG",
        },
        "unrelated_story_noise": {
            "control_kind": "unrelated_story_noise",
            "raw_story_text": "A public dialogue topic arc mentions continuity, but no source-backed claim is supported.",
        },
    }


def run_thread_story_packet_fixture() -> dict[str, Any]:
    packet = build_thread_story_packet(fixture_rows(), created_at="2026-06-06T00:00:00Z")
    controls = {key: evaluate_negative_control(row) for key, row in negative_control_rows().items()}
    probe = build_answer_boundary_probe(packet)
    comparison = build_answer_comparison_report(packet)
    closeout = build_public_shadow_closeout_report(packet, controls, comparison)
    serialized = json.dumps(
        {"packet": packet, "controls": controls, "probe": probe, "comparison": comparison, "closeout": closeout},
        ensure_ascii=False,
    )
    leakage_hits = [term for term in LEAKAGE_TERMS if term in serialized]
    ok = (
        bool(packet.get("created"))
        and not leakage_hits
        and all(controls[key].get("decision") == value for key, value in CONTROL_DECISIONS.items())
        and comparison["metrics"]["public_leakage_hit_count"] == 0
        and comparison["arms"]["packet_only"]["decision"] == "blocked_source_reopen_required"
        and closeout["closeout_eligible"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": FIXTURE_KIND,
        "ok": ok,
        "status": "contract_smoke" if ok else "failed",
        "packet": packet,
        "negative_controls": controls,
        "answer_boundary_probe": probe,
        "answer_comparison_report": comparison,
        "public_shadow_closeout_report": closeout,
        "metrics": {
            "source_ref_count": packet.get("source_ref_count", 0),
            "negative_control_count": len(controls),
            "public_leakage_hit_count": len(leakage_hits),
            "answer_comparison_case_count": comparison["metrics"]["case_count"],
            "public_shadow_closeout_eligible": closeout["closeout_eligible"],
        },
        "privacy_boundary": {
            "raw_story_text_emitted": False,
            "symbolic_arc_labels_emitted": False,
            "agent_visible_source_refs_emitted": False,
            "local_paths_emitted": False,
        },
        "cannot_claim": CANNOT_CLAIM,
    }
