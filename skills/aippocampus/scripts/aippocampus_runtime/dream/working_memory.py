#!/usr/bin/env python3
"""Project adjudicated dream findings onto soft working memory.

Dream synthesis and foreground recall delivery have different risk profiles.
This helper keeps the post-adjudication bridge small and explicit: raw dream
rows do not leave the holding queue, while background-adjudicated hypotheses
reuse the existing working-memory substrate instead of adding a parallel dream
channel or forcing the user to approve every dream.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.dream import (
    journey_bridges,
    probe_authority,
    trust_horizon_recovery,
)
from aippocampus_runtime.dream import (
    lifecycle as dream_lifecycle,
)
from aippocampus_runtime.dream.constructive_outputs import (
    clean_constructive_artifact,
    clean_prospective_invitation,
    prospective_invitation_block_reason,
    prospective_invitation_delivery_plan,
    prospective_invitation_silent_plan,
)
from aippocampus_runtime.dream.risk_terms import dream_text_hard_risk
from aippocampus_runtime.source.io_kernel import (
    merge_source_refs,
    parse_utc,
    safe_float,
    source_ref_key,
    source_ref_key_set,
)
from aippocampus_runtime.subconscious.candidate_router import (
    USE_WITH_SOURCE,
    ask_policy_for,
    trigger_terms_for,
)

SCHEMA_VERSION = 1
DREAM_FINDING_KIND = "dream_synthesized"
WORKING_MEMORY_KIND = "aippocampus_working_memory"
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"
ADJUDICATED_REVIEW_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}
ADJUDICATED_DREAM_DOWNSTREAM_USES = {
    "working_memory",
    "ambient_recall_card",
    "reflection_space",
}
DEFAULT_BACKGROUND_ADJUDICATION_SOURCE = "background_dream_adjudication"
LOW_SIGNAL_TERMS = {
    "question",
    "candidate",
    "thread",
    "source",
    "summary",
    "user",
    "work",
    "project",
}
DEFAULT_TRUST_HORIZON_INVALIDATION_TRIGGERS = (
    "source_fingerprint_changed",
    "contradiction_visible",
    "user_correction",
    "user_requested_evidence",
    "exact_or_quote_claim",
    "sensitive_claim",
    "trust_horizon_expired",
    "trust_horizon_review_due",
)


def stable_digest(*parts: object, prefix: str, length: int = 16) -> str:
    raw = "\n".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def is_present(value: object) -> bool:
    return value is not None and value != ""


def string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if is_present(item))
    return ()


def unique_preserve(values: Iterable[object], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), 90)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def text_terms(text: str) -> list[str]:
    terms = [
        token.casefold()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)
        if len(token) >= 3
    ]
    return [term for term in terms if term not in LOW_SIGNAL_TERMS]


def normalize_now(now: str | datetime | None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    parsed = parse_utc(str(now)) if now else parse_utc(now_utc())
    return parsed or datetime.now(timezone.utc)


def clean_dream_source_refs(value: object) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raw_items = []

    return tuple(
        merge_source_refs(
            [],
            raw_items,
            limit=max(1, len(raw_items)),
            require_anchor=False,
        )
    )


def bridge_claims_have_source_refs(finding: Mapping[str, Any]) -> bool:
    claims = [item for item in finding.get("bridge_claims") or [] if isinstance(item, Mapping)]
    if not claims:
        return False
    return all(clean_dream_source_refs(claim.get("source_refs")) for claim in claims)


def audit_failed(finding: Mapping[str, Any]) -> bool:
    audit = finding.get("source_ref_audit") or {}
    return isinstance(audit, Mapping) and str(audit.get("status") or "") == "failed"


def source_pack_is_ready(source_pack: Mapping[str, Any]) -> bool:
    if source_pack.get("kind") != "aippocampus_dream_input_pack":
        return False
    if source_pack.get("status") != "ready_for_dream_worker":
        return False
    audit = source_pack.get("source_ref_audit") or {}
    if isinstance(audit, Mapping) and audit.get("status") in {
        "missing_clean_source_refs",
        "insufficient_source_threads",
        "failed",
    }:
        return False
    return bool(clean_dream_source_refs(source_pack.get("source_refs")))


def source_pack_overlaps_finding(
    finding: Mapping[str, Any],
    source_pack: Mapping[str, Any],
) -> bool:
    finding_keys = source_ref_key_set(clean_dream_source_refs(finding.get("source_refs")))
    pack_keys = source_ref_key_set(clean_dream_source_refs(source_pack.get("source_refs")))
    return bool(finding_keys and pack_keys and finding_keys & pack_keys)


def sensitive_dream_hypothesis(finding: Mapping[str, Any]) -> bool:
    return dream_text_hard_risk(
        finding.get("title"),
        finding.get("summary"),
        finding.get("recommendation"),
        finding.get("counter_evidence"),
        finding.get("constructive_artifact"),
        finding.get("prospective_invitation"),
        finding.get("journey_bridge_hypothesis"),
    )


def project_label_from_refs(refs: Iterable[Mapping[str, Any]]) -> str | None:
    labels = unique_preserve(
        [str(ref.get("project_label") or "") for ref in refs if ref.get("project_label")],
        limit=3,
    )
    return labels[0] if len(labels) == 1 else None


def clean_working_memory_refs(
    refs: Iterable[Mapping[str, Any]], *, limit: int = 8
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        line = (
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
        )
        clean = {
            "thread_key": ref.get("thread_key") or ref.get("thread_id"),
            "title": ref.get("title"),
            "project_label": ref.get("project_label"),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (
            str(clean.get("thread_key") or ""),
            str(clean.get("line") or ""),
            str(clean.get("message_id") or ""),
        )
        if not any(key) or key in seen:
            continue
        seen.add(key)
        out.append({k: v for k, v in clean.items() if is_present(v)})
        if len(out) >= limit:
            break
    return out


def dream_source_fingerprint(refs: Iterable[Mapping[str, Any]]) -> str:
    keys = sorted(key for ref in refs if any(key := source_ref_key(ref)))
    return stable_digest(keys, prefix="dreamsrc", length=18)


def dream_trust_horizon(
    finding: Mapping[str, Any],
    refs: Iterable[Mapping[str, Any]],
    *,
    visibility_tier: str = "quiet_substrate",
) -> dict[str, Any]:
    """Build the #299 trust-horizon capsule for adjudicated dream findings.

    The horizon is a source-discipline control, not a truth upgrade. It lets a
    foreground consumer use an accepted capsule as quiet route context while
    naming exactly which changes force source reopen instead of letting the
    dream become a smoother long-lived summary.
    """

    validated_at = (
        finding.get("validated_at")
        or finding.get("adjudicated_at")
        or finding.get("reviewed_at")
        or finding.get("created_at")
        or now_utc()
    )
    validated_by = (
        finding.get("validated_by")
        or finding.get("adjudication_source")
        or DEFAULT_BACKGROUND_ADJUDICATION_SOURCE
    )
    triggers = unique_preserve(
        [
            *string_values(finding.get("invalidation_triggers")),
            *DEFAULT_TRUST_HORIZON_INVALIDATION_TRIGGERS,
        ],
        limit=16,
    )
    return {
        "schema_version": 1,
        "validated_at": str(validated_at),
        "validated_by": str(validated_by),
        "source_fingerprint": dream_source_fingerprint(refs),
        "review_after": finding.get("review_after") or finding.get("expires_or_review_after"),
        "expires_at": finding.get("expires_at"),
        "invalidation_triggers": triggers,
        "visibility_tier": visibility_tier,
        "ordinary_use": "quiet_route_context_without_reopen_until_invalidated",
        "truth_boundary": "trust_horizon_does_not_make_dream_a_source_fact",
    }


def adjudicated_dream_downstream_use(finding: Mapping[str, Any]) -> list[str]:
    requested = [
        str(item)
        for item in finding.get("downstream_use") or []
        if str(item) in ADJUDICATED_DREAM_DOWNSTREAM_USES
    ]
    return unique_preserve(requested or ["working_memory"], limit=3)


def adjudicated_dream_is_eligible(finding: Mapping[str, Any]) -> bool:
    if finding.get("finding_kind") != DREAM_FINDING_KIND:
        return False
    if str(finding.get("review_state") or "") not in ADJUDICATED_REVIEW_STATES:
        return False
    refs = clean_dream_source_refs(finding.get("source_refs"))
    if not refs:
        return False
    if audit_failed(finding):
        return False
    if not bridge_claims_have_source_refs(finding):
        return False
    if not journey_bridges.journey_bridge_present_is_valid(finding.get("journey_bridge_hypothesis")):
        return False
    return True


def background_adjudicate_dream_finding(
    finding: Mapping[str, Any],
    *,
    source_pack: Mapping[str, Any] | None = None,
    confidence_floor: float = 0.55,
    adjudication_source: str = DEFAULT_BACKGROUND_ADJUDICATION_SOURCE,
) -> dict[str, Any]:
    """Accept or park a dream finding using structural source-ref checks.

    This is intentionally not a user-review step. It is a deterministic guard
    for the background route: every projected hypothesis must keep clean-source
    handles on the finding and on each bridge claim, and pack-backed P2
    candidates must overlap the source pack that triggered them.
    """

    result = dict(finding)
    checks = {
        "dream_finding_kind": finding.get("finding_kind") == DREAM_FINDING_KIND,
        "source_refs_present": bool(clean_dream_source_refs(finding.get("source_refs"))),
        "source_ref_audit": not audit_failed(finding),
        "bridge_claims_source_refs": bridge_claims_have_source_refs(finding),
        "confidence_floor": safe_float(finding.get("confidence"), 0.62) >= confidence_floor,
        "sensitive_use_gate": not sensitive_dream_hypothesis(finding),
    }
    if source_pack is not None:
        checks["source_pack_ready"] = source_pack_is_ready(source_pack)
        checks["source_pack_overlap"] = source_pack_overlaps_finding(finding, source_pack)

    failed = [key for key, passed in checks.items() if not passed]
    passed = [key for key, passed in checks.items() if passed]
    result["adjudication_source"] = adjudication_source
    result["foreground_eligible"] = False
    result["formal_memory_eligible"] = False
    result["clean_source_mutation"] = False
    if failed:
        result["review_state"] = "needs_review"
        result["human_review_required"] = bool(result.get("human_review_required") or False)
        lifecycle_record = dream_lifecycle.dream_lifecycle_record(
            {
                **result,
                "adjudication_result": {
                    "status": "parked",
                    "passed_checks": passed,
                    "failed_checks": failed,
                    "policy": "background_source_guard_v1",
                },
            }
        )
        result["adjudication_result"] = {
            "status": "parked",
            "passed_checks": passed,
            "failed_checks": failed,
            "policy": "background_source_guard_v1",
            "readable_reason": lifecycle_record["readable_reason"],
            "next_review_or_cleanup": lifecycle_record["next_review_or_cleanup"],
        }
        result["dream_lifecycle"] = lifecycle_record
        result["lifecycle_state"] = lifecycle_record["state"]
        return result

    requested_uses = [
        *string_values(result.get("downstream_use")),
        "working_memory",
        "ambient_recall_card",
        "reflection_space",
    ]
    result["review_state"] = "agent_adjudicated"
    result["human_review_required"] = False
    result["downstream_use"] = [
        item
        for item in unique_preserve(requested_uses, limit=6)
        if item in ADJUDICATED_DREAM_DOWNSTREAM_USES
    ]
    result["adjudication_result"] = {
        "status": "accepted",
        "passed_checks": passed,
        "failed_checks": [],
        "policy": "background_source_guard_v1",
    }
    result["dream_lifecycle"] = dream_lifecycle.dream_lifecycle_record(result)
    result["lifecycle_state"] = result["dream_lifecycle"]["state"]
    return result


def background_adjudicate_dream_findings(
    findings: Iterable[Mapping[str, Any]],
    *,
    source_pack: Mapping[str, Any] | None = None,
    confidence_floor: float = 0.55,
    adjudication_source: str = DEFAULT_BACKGROUND_ADJUDICATION_SOURCE,
) -> list[dict[str, Any]]:
    return [
        background_adjudicate_dream_finding(
            finding,
            source_pack=source_pack,
            confidence_floor=confidence_floor,
            adjudication_source=adjudication_source,
        )
        for finding in findings
    ]


def adjudicated_dream_findings_to_working_memory(
    findings: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = 20,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if len(rows) >= max_rows:
            break
        if not adjudicated_dream_is_eligible(finding):
            continue
        raw_refs = clean_dream_source_refs(finding.get("source_refs"))
        refs = clean_working_memory_refs(raw_refs)
        if not refs:
            continue
        bridge_claims = [
            str(item.get("claim") or "")
            for item in finding.get("bridge_claims") or []
            if isinstance(item, Mapping)
        ]
        title = compact_text(str(finding.get("title") or "Adjudicated dream hypothesis"), 180)
        summary = compact_text(str(finding.get("summary") or ""), 760)
        project_label = project_label_from_refs(refs)
        source_finding_id = str(
            finding.get("dream_finding_id")
            or finding.get("fingerprint")
            or stable_digest(finding, prefix="dreamfinding", length=18)
        )
        concepts = unique_preserve(
            [
                str(finding.get("dream_function") or ""),
                str(finding.get("compensatory_kind") or ""),
                *text_terms(" ".join([title, summary, " ".join(bridge_claims)])),
            ],
            limit=18,
        )
        activation_cues = unique_preserve(finding.get("activation_cues") or [], limit=12)
        trust_horizon = dream_trust_horizon(finding, raw_refs)
        constructive_artifact = clean_constructive_artifact(finding.get("constructive_artifact"))
        prospective_invitation = clean_prospective_invitation(finding.get("prospective_invitation"))
        journey_bridge = journey_bridges.clean_journey_bridge_from_finding(finding)
        authority = probe_authority.authority_from_finding(finding)
        candidate = {
            "candidate_type": DREAM_HYPOTHESIS_TYPE,
            "title": title,
            "summary": summary,
            "recommendation": (
                "Use as an adjudicated dream hypothesis only when it changes the current answer; "
                "re-open clean source before factual claims."
            ),
        }
        trigger_terms = activation_cues or trigger_terms_for(candidate, concepts, project_label)
        if prospective_invitation:
            trigger_terms = unique_preserve(
                [
                    *trigger_terms,
                    prospective_invitation.get("trigger_condition"),
                    prospective_invitation.get("emerging_theme"),
                ],
                limit=12,
            )
        trigger_terms = journey_bridges.trigger_terms_with_journey_bridge(trigger_terms, journey_bridge)
        foreground_use = {
            "default_action": "quiet_substrate",
            "use_only_when_it_changes_current_answer": True, "strong_claim_requires_source_reopen": True,
            "accepted_capsule_can_be_used_quietly_until_invalidated": True,
            "stay_silent_when_source_visible": True,
            "stay_silent_when_annoyance_risk_high": True,
            "render_boundary": "dream_hypothesis_not_source_fact",
        }
        probe_authority.apply_foreground_use(authority, foreground_use)
        if constructive_artifact:
            foreground_use["draft_artifact_action"] = "optional_probe"
        if prospective_invitation:
            foreground_use["prospective_invitation_action"] = "optional_question_on_trigger"
        journey_bridges.add_journey_bridge_foreground_use(foreground_use, journey_bridge)
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": WORKING_MEMORY_KIND,
                "created_at": now_utc(),
                "status": "active",
                "trust_domain": "dream_working_memory",
                "route": USE_WITH_SOURCE,
                "ask_policy": ask_policy_for(USE_WITH_SOURCE),
                "risk": "medium",
                "route_reason": "adjudicated dream hypothesis with source refs can seed recall/reflection, but remains non-factual",
                "candidate_key": stable_digest(candidate, source_finding_id, prefix="wm_dream", length=18),
                "candidate_type": DREAM_HYPOTHESIS_TYPE,
                "title": title,
                "summary": summary,
                "recommendation": candidate["recommendation"],
                "confidence": round(float(finding.get("confidence") or 0.62), 4),
                "project_label": project_label,
                # Model-backed dream workers now own semantic activation. The
                # fallback keeps deterministic structural eval rows usable, but
                # live model-backed rows should arrive with activation_cues so
                # summary/scaffold prose cannot widen the trigger surface.
                "trigger_terms": trigger_terms,
                "activation_cues": activation_cues,
                "concepts": concepts,
                "source_finding_ids": [source_finding_id],
                "source_refs": refs,
                "source_fingerprint": trust_horizon["source_fingerprint"],
                "validated_at": trust_horizon["validated_at"],
                "validated_by": trust_horizon["validated_by"],
                "review_after": trust_horizon["review_after"],
                "invalidation_triggers": trust_horizon["invalidation_triggers"],
                "visibility_tier": trust_horizon["visibility_tier"],
                "source_strength": {
                    "score": probe_authority.source_strength_score(authority, len(refs)),
                    "source_ref_count": len(refs),
                    "source_thread_count": len({str(ref.get("thread_key") or "") for ref in refs}),
                    "source_line_count": sum(1 for ref in refs if ref.get("line")),
                    "source_finding_count": 1,
                },
                "source_candidate_batch_id": finding.get("batch_id"),
                "source_candidate_created_at": finding.get("created_at"),
                "review_state": finding.get("review_state"),
                "lifecycle_state": "adjudicated_source_ref_hypothesis",
                "dream_lifecycle": dream_lifecycle.dream_lifecycle_record(finding),
                "adjudication_source": finding.get("adjudication_source")
                or "background_dream_adjudication",
                "dream_function": finding.get("dream_function"),
                "dream_phase": finding.get("dream_phase"),
                "compensatory_kind": finding.get("compensatory_kind"),
                "downstream_use": adjudicated_dream_downstream_use(finding),
                "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                "expires_at": finding.get("expires_at"),
                "trust_horizon": trust_horizon,
                "foreground_use": foreground_use,
                "source_authority": dict(authority)
                if authority
                else {"state": "cross_thread_or_standard_probe", "not_foreground_truth": True},
                "sensitive_use_gate": {
                    "state": "blocked" if sensitive_dream_hypothesis(finding) else "allowed",
                    "human_or_user_intervention_required_for_direct_assertion": True,
                    "formal_memory_promotion_allowed": False,
                },
                "human_review_required": bool(finding.get("human_review_required") or False),
                "formal_memory_eligible": False,
                "clean_source_mutation": False,
            }
        )
        if constructive_artifact:
            rows[-1]["constructive_artifact"] = constructive_artifact
        if prospective_invitation:
            rows[-1]["prospective_invitation"] = prospective_invitation
        journey_bridges.attach_journey_bridge_to_row(rows[-1], journey_bridge)
    return rows


def trust_horizon_map(row: Mapping[str, Any]) -> Mapping[str, Any]:
    horizon = row.get("trust_horizon") or {}
    return horizon if isinstance(horizon, Mapping) else {}


def trust_horizon_timestamps(row: Mapping[str, Any], key: str) -> list[datetime]:
    horizon = trust_horizon_map(row)
    timestamps: list[datetime] = []
    for value in (row.get(key), horizon.get(key)):
        parsed = parse_utc(str(value or ""))
        if parsed:
            timestamps.append(parsed)
    return timestamps


def dream_hypothesis_expired(row: Mapping[str, Any], *, now: str | datetime | None = None) -> bool:
    now_dt = normalize_now(now)
    return any(expires_at <= now_dt for expires_at in trust_horizon_timestamps(row, "expires_at"))


def trust_horizon_status(row: Mapping[str, Any], *, now: str | datetime | None = None) -> str:
    now_dt = normalize_now(now)
    if any(expires_at <= now_dt for expires_at in trust_horizon_timestamps(row, "expires_at")):
        return "expired"
    if any(review_after <= now_dt for review_after in trust_horizon_timestamps(row, "review_after")):
        return "review_due"
    return "valid"


def plan_dream_hypothesis_use(
    row: Mapping[str, Any],
    *,
    prompt: str = "",
    route_relevance: bool | None = None,
    source_visible: bool = False,
    annoyance_risk: str = "low",
    strong_user_facing_claim: bool = False,
    exact_or_quote_claim: bool = False,
    sensitive_claim: bool = False,
    contradiction_visible: bool = False,
    user_correction_visible: bool = False,
    user_requested_evidence: bool = False,
    source_fingerprint_current: str | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        return {"action": "stay_silent", "reason": "not_dream_hypothesis"}
    if row.get("review_state") not in ADJUDICATED_REVIEW_STATES:
        return {"action": "stay_silent", "reason": "not_adjudicated"}
    horizon_status = trust_horizon_status(row, now=now)
    expired = dream_hypothesis_expired(row, now=now)
    invitation_diagnostic = None
    if expired:
        invitation_blocked = prospective_invitation_silent_plan(
            row,
            reason="dream_hypothesis_expired",
            diagnostic="delivery_gate_blocked",
        )
        invitation_diagnostic = (invitation_blocked or {}).get("invitation_diagnostic")
    early_plan = trust_horizon_recovery.invalidation_plan(
        row,
        trust_status=horizon_status,
        sensitive_blocked=(row.get("sensitive_use_gate") or {}).get("state") == "blocked" or bool(row.get("human_review_required")),
        expired=expired,
        invitation_diagnostic=invitation_diagnostic,
    )
    if early_plan:
        return early_plan
    if source_visible:
        return {"action": "stay_silent", "reason": "source_already_visible"}
    if str(annoyance_risk or "").casefold() in {"high", "annoying", "noisy"}:
        return {"action": "stay_silent", "reason": "annoyance_risk_high"}
    invitation_block_reason = prospective_invitation_block_reason(row)
    if invitation_block_reason:
        return {
            "action": "stay_silent",
            "reason": invitation_block_reason,
            "invitation_diagnostic": "annoyance_suppressed"
            if invitation_block_reason == "prospective_invitation_annoyance_high"
            else "delivery_gate_blocked",
        }
    horizon = row.get("trust_horizon") or {}
    stored_fingerprint = str(
        row.get("source_fingerprint")
        or (horizon.get("source_fingerprint") if isinstance(horizon, Mapping) else "")
        or ""
    )
    blocked_plan = trust_horizon_recovery.invalidation_plan(
        row,
        trust_status=horizon_status,
        source_fingerprint_changed=bool(source_fingerprint_current and stored_fingerprint and source_fingerprint_current != stored_fingerprint),
        contradiction_visible=contradiction_visible,
        user_correction_visible=user_correction_visible,
        user_requested_evidence=user_requested_evidence,
        exact_or_quote_claim=exact_or_quote_claim,
        sensitive_claim=sensitive_claim,
        strong_user_facing_claim=strong_user_facing_claim,
        review_due=horizon_status == "review_due",
    )
    if blocked_plan:
        return blocked_plan
    if route_relevance is None:
        haystack = " ".join(
            [
                str(row.get("title") or ""),
                str(row.get("summary") or ""),
                " ".join(string_values(row.get("trigger_terms"))),
                " ".join(string_values(row.get("concepts"))),
            ]
        ).casefold()
        prompt_terms = [term for term in text_terms(prompt) if len(term) >= 4]
        route_relevance = bool(prompt_terms and any(term in haystack for term in prompt_terms))
    if not route_relevance:
        trigger_miss = prospective_invitation_silent_plan(
            row,
            reason="trigger_not_matched",
            diagnostic="trigger_not_matched",
        )
        if trigger_miss:
            return trigger_miss
        return {"action": "stay_silent", "reason": "no_route_relevance"}
    matched_prompt_terms = text_terms(prompt)[:6]
    invitation_plan = prospective_invitation_delivery_plan(row, trust_horizon_status=horizon_status, matched_prompt_terms=matched_prompt_terms)
    if invitation_plan:
        return invitation_plan
    bridge_plan = journey_bridges.journey_bridge_delivery_plan_for_prompt(row, horizon_status, matched_prompt_terms)
    if bridge_plan:
        return bridge_plan
    return {
        "action": "use_quietly",
        "reason": "dream_hypothesis_changes_route_or_answer",
        "route": "working_memory",
        "requires_source_reopen": False,
        "truth_boundary": row.get("truth_boundary"),
        "trust_horizon_status": trust_horizon_status(row, now=now),
        "matched_prompt_terms": matched_prompt_terms,
    }


def render_dream_hypothesis_preview(row: Mapping[str, Any]) -> str:
    if bridge_preview := journey_bridges.render_journey_bridge_preview(row):
        return bridge_preview
    invitation = clean_prospective_invitation(row.get("prospective_invitation"))
    if invitation:
        opening = compact_text(str(invitation.get("suggested_opening") or ""), 180)
        return (
            f"Prospective Dream invitation, not source fact: {opening}. "
            "Ask only as an optional question when the trigger matches; reopen source before strong claims."
        )
    artifact = clean_constructive_artifact(row.get("constructive_artifact"))
    if artifact:
        draft = compact_text(str(artifact.get("draft_text") or ""), 180)
        return (
            f"Dream draft, not source fact: {draft}. "
            "Use only as an optional probe; reopen source before making a strong claim."
        )
    title = compact_text(str(row.get("title") or "Adjudicated dream hypothesis"), 160)
    return (
        f"Dream hypothesis, not source fact: {title}. "
        "Use quietly as route context; reopen source before making a strong claim."
    )


def reviewed_dream_findings_to_working_memory(
    findings: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = 20,
) -> list[dict[str, Any]]:
    return adjudicated_dream_findings_to_working_memory(findings, max_rows=max_rows)
