#!/usr/bin/env python3
"""Constructive Dream draft and invitation helpers.

These helpers keep synthetic Dream output useful without letting it become a
parallel source of truth. Drafts and invitations may shape a future agent's
question or route, but source refs, counter-evidence, expiry, annoyance, and
source-reopen boundaries stay attached at every projection step.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.dream.risk_terms import dream_text_hard_risk

CONSTRUCTIVE_ARTIFACT_FUNCTIONS = {"compensatory", "active_imagination"}
CONSTRUCTIVE_ARTIFACT_KINDS = {
    "draft_question",
    "draft_prompt",
    "draft_outline",
    "draft_probe",
}
CONSTRUCTIVE_ARTIFACT_USES = {
    "foreground_probe",
    "source_reopen_check",
    "planning_seed",
}
PROSPECTIVE_INVITATION_TYPES = {
    "prospective_open",
    "light_question",
    "source_reopen_first",
}
PROSPECTIVE_INVITATION_STATUSES = {
    "dream_invitation_not_source_fact",
}
ANNOYANCE_RISKS = {"low", "medium", "high"}

ResolveRefs = Callable[[object, Mapping[str, dict[str, Any]]], list[dict[str, Any]]]
FutureUtc = Callable[..., str]


def parse_duration_days(value: object, *, default_days: int) -> tuple[int, bool]:
    text = str(value or "").strip().casefold()
    if not text:
        return default_days, False
    if text.endswith("d"):
        raw_number = text[:-1]
    elif text.endswith("day") or text.endswith("days"):
        raw_number = text.split("day", 1)[0].strip()
    else:
        raw_number = text
    try:
        days = int(raw_number)
    except ValueError:
        return default_days, False
    if days < 1 or days > 90:
        return default_days, False
    return days, True


def normalized_constructive_artifact(
    candidate: Mapping[str, Any],
    *,
    dream_function: str,
    by_id: Mapping[str, dict[str, Any]],
    resolve_refs: ResolveRefs,
) -> tuple[dict[str, Any] | None, list[str], bool]:
    raw = candidate.get("constructive_artifact")
    if raw is None:
        return None, [], False
    if not isinstance(raw, Mapping):
        return None, ["constructive_artifact_not_object"], False

    failures: list[str] = []
    if dream_function not in CONSTRUCTIVE_ARTIFACT_FUNCTIONS:
        failures.append("constructive_artifact_unsupported_dream_function")
    artifact_kind = str(raw.get("artifact_kind") or "")
    intended_use = str(raw.get("intended_use") or "")
    status = str(raw.get("status") or "")
    if artifact_kind not in CONSTRUCTIVE_ARTIFACT_KINDS:
        failures.append("constructive_artifact_invalid_kind")
    if intended_use not in CONSTRUCTIVE_ARTIFACT_USES:
        failures.append("constructive_artifact_invalid_intended_use")
    if status != "dream_draft_not_source":
        failures.append("constructive_artifact_invalid_status")

    draft_text = compact_text(str(raw.get("draft_text") or ""), 520)
    draft_origin = compact_text(str(raw.get("draft_origin") or ""), 180)
    if not draft_text:
        failures.append("constructive_artifact_missing_draft_text")
    refs = resolve_refs(raw.get("source_ref_ids"), by_id)
    if not refs:
        failures.append("constructive_artifact_missing_source_refs")
    counter_evidence = _string_list(raw.get("counter_evidence"), limit=6)
    when_not_to_use = _string_list(raw.get("when_not_to_use"), limit=8)
    if not counter_evidence:
        failures.append("constructive_artifact_missing_counter_evidence")
    if not when_not_to_use:
        failures.append("constructive_artifact_missing_when_not_to_use")

    sensitive_risk = dream_text_hard_risk(
        draft_text,
        draft_origin,
        " ".join(counter_evidence),
        " ".join(when_not_to_use),
    )
    if sensitive_risk:
        failures.append("sensitive_or_profile_artifact_requires_human_review")

    artifact = {
        "artifact_kind": artifact_kind,
        "draft_text": draft_text,
        "draft_origin": draft_origin,
        "intended_use": intended_use,
        "status": "dream_draft_not_source",
        "truth_boundary": "dream_draft_not_source",
        "source_refs": refs[:8],
        "counter_evidence": counter_evidence,
        "when_not_to_use": when_not_to_use,
        "foreground_use": "optional_probe_not_evidence",
        "requires_source_reopen_before_claim": True,
    }
    return {key: value for key, value in artifact.items() if value}, failures, sensitive_risk


def normalized_prospective_invitation(
    candidate: Mapping[str, Any],
    *,
    dream_function: str,
    by_id: Mapping[str, dict[str, Any]],
    resolve_refs: ResolveRefs,
    future_utc: FutureUtc,
) -> tuple[dict[str, Any] | None, list[str]]:
    raw = candidate.get("prospective_invitation")
    if raw is None:
        return None, []
    if not isinstance(raw, Mapping):
        return None, ["prospective_invitation_not_object"]

    failures: list[str] = []
    if dream_function != "prospective":
        failures.append("prospective_invitation_unsupported_dream_function")
    invitation_type = str(raw.get("invitation_type") or "")
    status = str(raw.get("status") or "")
    annoyance_risk = str(raw.get("annoyance_risk") or "medium").casefold()
    if invitation_type not in PROSPECTIVE_INVITATION_TYPES:
        failures.append("prospective_invitation_invalid_type")
    if status not in PROSPECTIVE_INVITATION_STATUSES:
        failures.append("prospective_invitation_invalid_status")
    if annoyance_risk not in ANNOYANCE_RISKS:
        failures.append("prospective_invitation_invalid_annoyance_risk")
        annoyance_risk = "medium"

    emerging_theme = compact_text(str(raw.get("emerging_theme") or ""), 240)
    trigger_condition = compact_text(str(raw.get("trigger_condition") or ""), 260)
    suggested_opening = compact_text(str(raw.get("suggested_opening") or ""), 360)
    if not trigger_condition:
        failures.append("prospective_invitation_missing_trigger_condition")
    if not suggested_opening:
        failures.append("prospective_invitation_missing_suggested_opening")
    refs = resolve_refs(raw.get("source_ref_ids"), by_id)
    if not refs:
        failures.append("prospective_invitation_missing_source_refs")
    expires_days, duration_ok = parse_duration_days(raw.get("expires_after"), default_days=14)
    if not duration_ok:
        failures.append("prospective_invitation_invalid_expiry")
    if dream_text_hard_risk(emerging_theme, trigger_condition, suggested_opening):
        failures.append("sensitive_or_profile_invitation_requires_human_review")

    invitation = {
        "emerging_theme": emerging_theme,
        "trigger_condition": trigger_condition,
        "suggested_opening": suggested_opening,
        "invitation_type": invitation_type,
        "expires_after": f"{expires_days}d",
        "expires_at": future_utc(days=expires_days),
        "annoyance_risk": annoyance_risk,
        "status": "dream_invitation_not_source_fact",
        "truth_boundary": "dream_invitation_not_source_fact",
        "source_refs": refs[:8],
        "foreground_use": "optional_question_on_trigger",
        "requires_source_reopen_before_claim": True,
    }
    return {key: value for key, value in invitation.items() if value}, failures


def projection_value_present(value: object) -> bool:
    return value is not None and value != "" and value != []


def clean_constructive_artifact(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    status = str(raw.get("status") or "")
    if status != "dream_draft_not_source":
        return None
    artifact = {
        "artifact_kind": compact_text(str(raw.get("artifact_kind") or ""), 80),
        "draft_text": compact_text(str(raw.get("draft_text") or ""), 520),
        "draft_origin": compact_text(str(raw.get("draft_origin") or ""), 180),
        "intended_use": compact_text(str(raw.get("intended_use") or ""), 80),
        "status": status,
        "truth_boundary": "dream_draft_not_source",
        "counter_evidence": _unique_preserve(raw.get("counter_evidence") or [], limit=6),
        "when_not_to_use": _unique_preserve(raw.get("when_not_to_use") or [], limit=8),
        "foreground_use": "optional_probe_not_evidence",
        "requires_source_reopen_before_claim": bool(
            raw.get("requires_source_reopen_before_claim") is not False
        ),
    }
    return {key: value for key, value in artifact.items() if projection_value_present(value)}


def clean_prospective_invitation(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    status = str(raw.get("status") or "")
    if status != "dream_invitation_not_source_fact":
        return None
    annoyance_risk = str(raw.get("annoyance_risk") or "medium").casefold()
    if annoyance_risk not in ANNOYANCE_RISKS:
        annoyance_risk = "medium"
    invitation = {
        "emerging_theme": compact_text(str(raw.get("emerging_theme") or ""), 240),
        "trigger_condition": compact_text(str(raw.get("trigger_condition") or ""), 260),
        "suggested_opening": compact_text(str(raw.get("suggested_opening") or ""), 360),
        "invitation_type": compact_text(str(raw.get("invitation_type") or ""), 80),
        "expires_after": compact_text(str(raw.get("expires_after") or ""), 40),
        "expires_at": raw.get("expires_at"),
        "annoyance_risk": annoyance_risk,
        "status": status,
        "truth_boundary": "dream_invitation_not_source_fact",
        "foreground_use": "optional_question_on_trigger",
        "requires_source_reopen_before_claim": bool(
            raw.get("requires_source_reopen_before_claim") is not False
        ),
    }
    return {key: value for key, value in invitation.items() if projection_value_present(value)}


def prospective_invitation_block_reason(row: Mapping[str, Any]) -> str:
    raw_invitation = row.get("prospective_invitation")
    if isinstance(raw_invitation, Mapping):
        status = str(raw_invitation.get("status") or "")
        if status != "dream_invitation_not_source_fact":
            return "prospective_invitation_invalid_status"
    invitation = clean_prospective_invitation(raw_invitation)
    if not invitation:
        return ""
    if str(invitation.get("annoyance_risk") or "").casefold() == "high":
        return "prospective_invitation_annoyance_high"
    retrospective = str(row.get("invitation_retrospective_status") or "").casefold()
    if retrospective in {"ignored", "rejected", "refuted", "stale", "superseded"}:
        return f"prospective_invitation_{retrospective}"
    return ""


def prospective_invitation_match_use(row: Mapping[str, Any]) -> dict[str, Any] | None:
    invitation = clean_prospective_invitation(row.get("prospective_invitation"))
    if not invitation or not invitation.get("suggested_opening"):
        return None
    return {
        "action": "deliver_as_optional_question",
        "reason": "matched_prospective_invitation_trigger",
        "invitation_diagnostic": "delivered_as_optional_question",
        "truth_boundary": invitation.get("truth_boundary") or row.get("truth_boundary"),
        "strong_claim_requires_source_reopen": True,
        "render_boundary": "dream_invitation_not_source_fact",
        "suggested_opening": compact_text(str(invitation.get("suggested_opening") or ""), 360),
        "invitation_type": invitation.get("invitation_type"),
    }


def prospective_invitation_delivery_plan(
    row: Mapping[str, Any],
    *,
    trust_horizon_status: str,
    matched_prompt_terms: list[str],
) -> dict[str, Any] | None:
    invitation = clean_prospective_invitation(row.get("prospective_invitation"))
    if not invitation:
        return None
    return {
        "action": "deliver_as_optional_question",
        "reason": "prospective_invitation_trigger_matched",
        "invitation_diagnostic": "delivered_as_optional_question",
        "route": "working_memory",
        "requires_source_reopen": bool(
            invitation.get("invitation_type") == "source_reopen_first"
            or invitation.get("requires_source_reopen_before_claim")
        ),
        "truth_boundary": invitation.get("truth_boundary") or row.get("truth_boundary"),
        "trust_horizon_status": trust_horizon_status,
        "suggested_opening": invitation.get("suggested_opening"),
        "invitation_type": invitation.get("invitation_type"),
        "render_boundary": "dream_invitation_not_source_fact",
        "matched_prompt_terms": matched_prompt_terms,
    }


def prospective_invitation_silent_plan(
    row: Mapping[str, Any],
    *,
    reason: str,
    diagnostic: str,
) -> dict[str, Any] | None:
    raw_invitation = row.get("prospective_invitation")
    if not isinstance(raw_invitation, Mapping):
        return None
    return {"action": "stay_silent", "reason": reason, "invitation_diagnostic": diagnostic}


def _string_list(value: object, *, limit: int, max_chars: int = 180) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    return _unique_preserve(
        [compact_text(str(item or ""), max_chars) for item in raw_items],
        limit=limit,
    )


def _unique_preserve(values: object, *, limit: int) -> list[str]:
    if isinstance(values, str):
        iterable = [values]
    elif isinstance(values, list):
        iterable = values
    else:
        iterable = []
    seen: set[str] = set()
    out: list[str] = []
    for value in iterable:
        text = compact_text(str(value or ""), 180)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out
