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

from aippocampuslib import compact_text, now_utc
from memory_candidate_router import USE_WITH_SOURCE, ask_policy_for, trigger_terms_for

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
SENSITIVE_DREAM_TERMS = {
    "diagnosis",
    "identity",
    "mental health",
    "personality",
    "preference",
    "prefers",
    "profile",
    "relationship",
    "secretly",
    "trauma",
    "人格",
    "关系",
    "创伤",
    "偏好",
    "诊断",
}
HIGH_CONFIDENCE_DREAM_THRESHOLD = 0.88
SENSITIVE_BOUNDARY_COPY = (
    "not as a user-profile fact",
    "not as user-profile fact",
    "not a user-profile fact",
    "do not treat this as a user-profile fact",
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


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_now(now: str | datetime | None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    parsed = parse_utc(str(now)) if now else parse_utc(now_utc())
    return parsed or datetime.now(timezone.utc)


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(
            ref.get("source_id")
            or ref.get("source_line")
            or ref.get("line")
            or ref.get("source_ref")
            or ""
        ),
    )


def source_ref_keys(refs: Iterable[Mapping[str, Any]]) -> set[tuple[str, str, str, str]]:
    return {source_ref_key(ref) for ref in refs if any(source_ref_key(ref))}


def normalize_source_refs(value: object) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = []

    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = dict(item)
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in ref.items() if is_present(v)})
    return tuple(refs)


def bridge_claims_have_source_refs(finding: Mapping[str, Any]) -> bool:
    claims = [item for item in finding.get("bridge_claims") or [] if isinstance(item, Mapping)]
    if not claims:
        return False
    return all(normalize_source_refs(claim.get("source_refs")) for claim in claims)


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
    return bool(normalize_source_refs(source_pack.get("source_refs")))


def source_pack_overlaps_finding(
    finding: Mapping[str, Any],
    source_pack: Mapping[str, Any],
) -> bool:
    finding_keys = source_ref_keys(normalize_source_refs(finding.get("source_refs")))
    pack_keys = source_ref_keys(normalize_source_refs(source_pack.get("source_refs")))
    return bool(finding_keys and pack_keys and finding_keys & pack_keys)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def sensitive_dream_hypothesis(finding: Mapping[str, Any]) -> bool:
    text = " ".join(
        [
            str(finding.get("title") or ""),
            str(finding.get("summary") or ""),
            str(finding.get("recommendation") or ""),
            " ".join(string_values(finding.get("counter_evidence"))),
        ]
    ).casefold()
    # Dream candidates often carry negative safety copy such as "not as a
    # user-profile fact". That phrase should protect against profile claims,
    # not become the reason a harmless hypothesis is parked.
    for phrase in SENSITIVE_BOUNDARY_COPY:
        text = text.replace(phrase, " ")
    if any(term in text for term in SENSITIVE_DREAM_TERMS):
        return True
    return safe_float(finding.get("confidence"), 0.0) > HIGH_CONFIDENCE_DREAM_THRESHOLD


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
    refs = normalize_source_refs(finding.get("source_refs"))
    if not refs:
        return False
    if audit_failed(finding):
        return False
    if not bridge_claims_have_source_refs(finding):
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
        "source_refs_present": bool(normalize_source_refs(finding.get("source_refs"))),
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
        result["adjudication_result"] = {
            "status": "parked",
            "passed_checks": passed,
            "failed_checks": failed,
            "policy": "background_source_guard_v1",
        }
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
        refs = clean_working_memory_refs(finding.get("source_refs") or [])
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
        candidate = {
            "candidate_type": DREAM_HYPOTHESIS_TYPE,
            "title": title,
            "summary": summary,
            "recommendation": (
                "Use as an adjudicated dream hypothesis only when it changes the current answer; "
                "re-open clean source before factual claims."
            ),
        }
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": WORKING_MEMORY_KIND,
                "created_at": now_utc(),
                "status": "active",
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
                "trigger_terms": activation_cues or trigger_terms_for(candidate, concepts, project_label),
                "activation_cues": activation_cues,
                "concepts": concepts,
                "source_finding_ids": [source_finding_id],
                "source_refs": refs,
                "source_strength": {
                    "score": 1.0 if len(refs) >= 2 else 0.75,
                    "source_ref_count": len(refs),
                    "source_thread_count": len({str(ref.get("thread_key") or "") for ref in refs}),
                    "source_line_count": sum(1 for ref in refs if ref.get("line")),
                    "source_finding_count": 1,
                },
                "source_candidate_batch_id": finding.get("batch_id"),
                "source_candidate_created_at": finding.get("created_at"),
                "review_state": finding.get("review_state"),
                "adjudication_source": finding.get("adjudication_source")
                or "background_dream_adjudication",
                "dream_function": finding.get("dream_function"),
                "dream_phase": finding.get("dream_phase"),
                "compensatory_kind": finding.get("compensatory_kind"),
                "downstream_use": adjudicated_dream_downstream_use(finding),
                "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                "expires_at": finding.get("expires_at"),
                "foreground_use": {
                    "default_action": "quiet_substrate",
                    "use_only_when_it_changes_current_answer": True,
                    "strong_claim_requires_source_reopen": True,
                    "stay_silent_when_source_visible": True,
                    "stay_silent_when_annoyance_risk_high": True,
                    "render_boundary": "dream_hypothesis_not_source_fact",
                },
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
    return rows


def dream_hypothesis_expired(row: Mapping[str, Any], *, now: str | datetime | None = None) -> bool:
    expires_at = parse_utc(str(row.get("expires_at") or ""))
    return bool(expires_at and expires_at <= normalize_now(now))


def plan_dream_hypothesis_use(
    row: Mapping[str, Any],
    *,
    prompt: str = "",
    route_relevance: bool | None = None,
    source_visible: bool = False,
    annoyance_risk: str = "low",
    strong_user_facing_claim: bool = False,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        return {"action": "stay_silent", "reason": "not_dream_hypothesis"}
    if row.get("review_state") not in ADJUDICATED_REVIEW_STATES:
        return {"action": "stay_silent", "reason": "not_adjudicated"}
    if (row.get("sensitive_use_gate") or {}).get("state") == "blocked" or row.get("human_review_required"):
        return {"action": "stay_silent", "reason": "sensitive_review_required"}
    if dream_hypothesis_expired(row, now=now):
        return {"action": "stay_silent", "reason": "dream_hypothesis_expired"}
    if source_visible:
        return {"action": "stay_silent", "reason": "source_already_visible"}
    if str(annoyance_risk or "").casefold() in {"high", "annoying", "noisy"}:
        return {"action": "stay_silent", "reason": "annoyance_risk_high"}
    if strong_user_facing_claim:
        return {
            "action": "reopen_source",
            "reason": "strong_claim_requires_source_reopen",
            "requires_source_reopen": True,
            "truth_boundary": row.get("truth_boundary"),
        }
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
        return {"action": "stay_silent", "reason": "no_route_relevance"}
    return {
        "action": "use_quietly",
        "reason": "dream_hypothesis_changes_route_or_answer",
        "route": "working_memory",
        "requires_source_reopen": False,
        "truth_boundary": row.get("truth_boundary"),
        "matched_prompt_terms": text_terms(prompt)[:6],
    }


def render_dream_hypothesis_preview(row: Mapping[str, Any]) -> str:
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
