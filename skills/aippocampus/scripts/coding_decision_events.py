#!/usr/bin/env python3
"""Extract source-backed coding decision events from clean source.

This deterministic slice turns clean-source user/final turns into staging
`decision_event` candidates and compact coding-continuity tickets. It is not a
code index, not a hook policy, and not formal memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.navigation.associations import (
    extract_terms_from_text,
    normalize_term,
    source_text_is_noise,
)
from aippocampus_runtime.question.source_refs import source_ref_key
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampuslib import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    sanitize_external_model_text,
)
from correction_reconsolidation import (
    ADJUDICATION_KIND,
    route_for_adjudication,
    sanitize_file_hints,
    should_surface_candidate,
)
from registry import unique_preserve

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-coding-decision-events-v1"

DECISION_KIND = "aippocampus_coding_decision_candidate"
ASSESSMENT_KIND = "aippocampus_coding_decision_state_assessment"
TICKET_KIND = "aippocampus_coding_continuity_ticket"

EVENT_TYPES = (
    "accepted_decision",
    "rejected_route",
    "scope_narrowing",
    "do_not_repeat",
    "user_correction",
)
REVIEW_STATUSES = (
    "adopted",
    "refuted",
    "stale",
    "superseded",
    "local_only",
    "needs_confirmation",
)
TICKET_TRIGGERS = ("session_start", "compaction_loss", "pre_patch", "rejected_route")
SURFACEABLE_STATUSES = {"adopted"}
SURFACEABLE_EVENT_TYPES = {"rejected_route", "scope_narrowing", "do_not_repeat", "user_correction"}
THIN_SOURCE_SAFE_USES = {"refresh_sources", "ask"}
TICKET_FEEDBACK_OUTCOMES = (
    "accepted",
    "ignored",
    "dismissed",
    "corrected",
    "tool_success",
    "tool_failure",
)

REJECTED_PATTERNS = [
    r"\bdo not\b",
    r"\bdon't\b",
    r"\bavoid\b",
    r"\brejected\b",
    r"\bnot repeat\b",
    r"\bmust not\b",
    r"\bshould not\b",
    r"\bnot replace\b",
    r"不要",
    r"别",
    r"不能",
    r"不要再",
    r"不要把",
]
ACCEPTED_PATTERNS = [
    r"\bwe chose\b",
    r"\bwe decided\b",
    r"\badopted\b",
    r"\bimplemented\b",
    r"\blanded\b",
    r"\bkept\b",
    r"决定",
    r"采用",
    r"落地",
    r"保留",
]
SCOPE_PATTERNS = [
    r"\bscope\b",
    r"\bonly\b",
    r"\bdocs only\b",
    r"\bkeep .* narrow\b",
    r"只",
    r"只改",
    r"范围",
    r"收口",
]
CORRECTION_PATTERNS = [
    r"\bactually\b",
    r"\bcorrection\b",
    r"\bto be precise\b",
    r"\bnot .* but\b",
    r"纠正",
    r"更正",
    r"不是.*而是",
]
REFUTED_PATTERNS = [r"\brefuted\b", r"\bwrong\b", r"\bcontradicted\b", r"证伪", r"错误"]
SUPERSEDED_PATTERNS = [r"\bsuperseded\b", r"\breplaced\b", r"\bno longer\b", r"取代", r"不再"]
LOCAL_ONLY_PATTERNS = [r"\bbranch[- ]local\b", r"\bthis branch\b", r"\bthis task\b", r"本轮", r"当前分支"]

PATH_RE = re.compile(r"(?<![\w:/\\])[\w./\\-]+\.(?:py|ts|tsx|js|jsx|rs|md|json|toml|ya?ml)")
SYMBOL_RE = re.compile(r"`([^`]{2,80})`")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return f"{prefix}_{sha1_text(raw)[:length]}"


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def sanitize_text(value: Any, *, max_chars: int = 520) -> tuple[str, dict[str, Any]]:
    sanitized, policy = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, max_chars), policy


def privacy_scan(policies: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    redaction_types: list[str] = []
    redaction_count = 0
    hard_block = False
    for policy in policies:
        redaction_count += int(policy.get("redaction_count") or 0)
        hard_block = hard_block or bool(policy.get("hard_block"))
        redaction_types.extend(str(item) for item in policy.get("redaction_types") or [])
    return {
        "raw_text_stored": False,
        "local_paths_stored": False,
        "secrets_stored": False,
        "redacted": bool(redaction_count or hard_block),
        "redaction_count": redaction_count,
        "redaction_types": unique_preserve(redaction_types, limit=8),
        "hard_block": hard_block,
    }


def regex_any(patterns: Sequence[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def event_types_for_text(text: str, role: str) -> list[str]:
    low = text.casefold()
    event_types: list[str] = []
    if regex_any(REJECTED_PATTERNS, low):
        event_types.append("do_not_repeat" if "repeat" in low or "再" in low else "rejected_route")
    if regex_any(SCOPE_PATTERNS, low):
        event_types.append("scope_narrowing")
    if role == "user" and regex_any(CORRECTION_PATTERNS, low):
        event_types.append("user_correction")
    if role == "assistant" and regex_any(ACCEPTED_PATTERNS, low):
        event_types.append("accepted_decision")
    return unique_preserve(event_types, limit=4)


def source_ref_for_message(message: Mapping[str, Any], *, thread_key: str | None = None) -> dict[str, Any]:
    ref = {
        "thread_key": thread_key or message.get("thread_key"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "source_id": message.get("source_id"),
        "clean_ordinal": message.get("clean_ordinal"),
        "source_line": message.get("source_line"),
        "role": message.get("role"),
        "phase": message.get("phase") or "",
        "timestamp": message.get("timestamp"),
    }
    return {key: value for key, value in ref.items() if value not in {None, ""}}


def merge_source_refs(refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for ref in refs:
        key = source_ref_key(ref)
        if not key[0] or not any(key[1:]) or key in seen:
            continue
        seen.add(key)
        out.append(dict(ref))
    return out[:8]


def group_messages_by_turn(messages: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    fallback_index = 0
    for message in messages:
        turn_id = str(message.get("turn_id") or "")
        if not turn_id:
            fallback_index += 1
            turn_id = f"fallback:{fallback_index}"
        groups.setdefault(turn_id, []).append(message)
    return list(groups.values())


def scope_from_text(text: str, *, workspace: str | None = None) -> dict[str, Any]:
    policies: list[dict[str, Any]] = []
    paths = sanitize_file_hints(PATH_RE.findall(text), workspace=workspace, policies=policies)
    symbol_values = [
        value
        for value in SYMBOL_RE.findall(text)
        if "." not in value and "/" not in value and "\\" not in value and len(value.split()) <= 4
    ]
    modules = [
        normalize_term(Path(str(item.get("path") or "")).stem)
        for item in paths
        if item.get("path_kind") == "repo_relative"
    ]
    return {
        "files": paths[:8],
        "modules": unique_preserve([value for value in modules if value], limit=8),
        "symbols": unique_preserve(symbol_values, limit=8),
    }


def has_concrete_scope(affected_scope: Mapping[str, Any]) -> bool:
    return bool(
        affected_scope.get("files")
        or affected_scope.get("modules")
        or affected_scope.get("symbols")
    )


def classify_review_status(
    text: str,
    event_type: str,
    confidence: float,
    *,
    affected_scope: Mapping[str, Any],
    trigger_terms: Sequence[str],
) -> str:
    low = text.casefold()
    if regex_any(REFUTED_PATTERNS, low):
        return "refuted"
    if regex_any(SUPERSEDED_PATTERNS, low):
        return "superseded"
    if regex_any(LOCAL_ONLY_PATTERNS, low):
        return "local_only"
    if "old" in low and event_type == "rejected_route":
        return "stale"
    if confidence < 0.56:
        return "needs_confirmation"
    if event_type != "accepted_decision" and not (
        has_concrete_scope(affected_scope) or len(trigger_terms) >= 4
    ):
        # A source-backed coding constraint can be real and still too broad to
        # become foreground guidance. Keep broad or branch-ambiguous decisions
        # as staging hypotheses until review narrows their applicability.
        return "needs_confirmation"
    return "adopted"


def confidence_for(event_type: str, text: str, source_refs: Sequence[Mapping[str, Any]]) -> float:
    base = {
        "accepted_decision": 0.62,
        "rejected_route": 0.70,
        "scope_narrowing": 0.66,
        "do_not_repeat": 0.74,
        "user_correction": 0.64,
    }.get(event_type, 0.5)
    if len(source_refs) >= 2:
        base += 0.06
    if "`" in text or PATH_RE.search(text):
        base += 0.05
    if regex_any(LOCAL_ONLY_PATTERNS + SUPERSEDED_PATTERNS + REFUTED_PATTERNS, text):
        base += 0.03
    return round(min(0.95, base), 4)


def sentence_surface(text: str, event_type: str) -> str:
    sentences = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    for sentence in sentences:
        if event_type in event_types_for_text(sentence, "user") or event_type in event_types_for_text(
            sentence, "assistant"
        ):
            return compact_text(sentence, 420)
    return compact_text(text, 420)


def build_decision_candidate(
    *,
    event_type: str,
    text: str,
    role: str,
    source_refs: Sequence[Mapping[str, Any]],
    workspace: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any] | None:
    refs = merge_source_refs(source_refs)
    if not refs:
        return None
    policies: list[dict[str, Any]] = []
    surface_raw = sentence_surface(text, event_type)
    surface, policy = sanitize_text(surface_raw, max_chars=420)
    policies.append(policy)
    if not surface or source_text_is_noise(surface):
        return None
    affected_scope = scope_from_text(text, workspace=workspace)
    trigger_terms = trigger_terms_for(surface, affected_scope)
    extraction_confidence = confidence_for(event_type, text, refs)
    review_status = classify_review_status(
        text,
        event_type,
        extraction_confidence,
        affected_scope=affected_scope,
        trigger_terms=trigger_terms,
    )
    rejected_paths = []
    constraints = []
    chosen_path = ""
    if event_type in {"rejected_route", "do_not_repeat", "scope_narrowing", "user_correction"}:
        rejected_paths.append(
            {
                "path": surface,
                "why_rejected": "source-backed rejected-route or constraint language",
            }
        )
        constraints.append(surface)
    if event_type == "accepted_decision":
        chosen_path = surface
    decision_id = stable_id(
        "decision",
        event_type,
        surface,
        [source_ref_key(ref) for ref in refs],
        length=20,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "finding_kind": "decision_event",
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "decision_id": decision_id,
        "event_type": event_type,
        "status": "staging",
        "review_status": review_status,
        "source_review_status": review_status,
        "truth_status": "candidate_hypothesis_until_reviewed",
        "evidence_status": "source_backed",
        "source_role": role,
        "source_refs": refs,
        "affected_scope": affected_scope,
        "chosen_path": chosen_path,
        "rejected_paths": rejected_paths,
        "constraints": constraints,
        "extraction_confidence": extraction_confidence,
        "trigger_terms": trigger_terms,
        "formal_memory_promoted": False,
        "candidate_type": "coding_decision_event",
        "title": compact_text(f"Coding decision: {event_type.replace('_', ' ')}", 140),
        "summary": surface,
        "privacy_scan": privacy_scan(policies),
    }


def trigger_terms_for(surface: str, affected_scope: Mapping[str, Any]) -> list[str]:
    values = [surface]
    values.extend(str(item.get("path") or "") for item in affected_scope.get("files") or [])
    values.extend(str(item) for item in affected_scope.get("modules") or [])
    values.extend(str(item) for item in affected_scope.get("symbols") or [])
    terms = extract_terms_from_text("\n".join(values), limit=20) + split_query_terms(values)
    out = []
    for term in terms:
        normalized = normalize_term(str(term))
        if len(normalized) < 3 or normalized.casefold() in {"the", "and", "not", "use", "route"}:
            continue
        out.append(normalized)
    return unique_preserve(out, limit=16)


def extract_decision_candidates(
    messages: Sequence[Mapping[str, Any]],
    *,
    thread_key: str | None = None,
    workspace: str | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for turn_messages in group_messages_by_turn(messages):
        refs = [
            source_ref_for_message(message, thread_key=thread_key)
            for message in turn_messages
            if message.get("text")
        ]
        for message in turn_messages:
            text = str(message.get("text") or "")
            if not text.strip() or source_text_is_noise(text):
                continue
            role = str(message.get("role") or "")
            if role not in {"user", "assistant"}:
                continue
            if role == "assistant" and not (message.get("is_final") or message.get("phase") == "final_answer"):
                continue
            for event_type in event_types_for_text(text, role):
                candidate = build_decision_candidate(
                    event_type=event_type,
                    text=text,
                    role=role,
                    source_refs=refs,
                    workspace=workspace,
                )
                if not candidate:
                    continue
                key = str(candidate.get("decision_id") or "")
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            str((item.get("source_refs") or [{}])[0].get("source_line") or ""),
            str(item.get("event_type") or ""),
        ),
    )


def review_decision_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reviewed: list[dict[str, Any]] = []
    for candidate in candidates:
        copy = dict(candidate)
        status = str(copy.get("source_review_status") or copy.get("review_status") or "needs_confirmation")
        if status not in REVIEW_STATUSES:
            status = "needs_confirmation"
        copy["review_status"] = status
        copy["source_review_status"] = status
        # Decision events are terrain: source-backed records of what was said
        # then. Current-validity weather such as freshness or still-rejected
        # status is recomputed into ASSESSMENT_KIND rows below so stale source
        # cannot quietly become foreground authority.
        copy.pop("freshness", None)
        copy.pop("confidence", None)
        cleaned_rejected_paths = []
        for item in copy.get("rejected_paths") or []:
            if not isinstance(item, Mapping):
                continue
            cleaned = dict(item)
            cleaned.pop("still_rejected", None)
            cleaned_rejected_paths.append(cleaned)
        copy["rejected_paths"] = cleaned_rejected_paths
        copy["review_boundary"] = {
            "deterministic_prototype": True,
            "model_output": "none",
            "formal_memory": False,
            "review_or_validation_required": status != "adopted",
            "current_validity_weather_stored_on_event": False,
        }
        reviewed.append(copy)
    return reviewed


def prompt_matches_candidate(prompt: str, candidate: Mapping[str, Any]) -> bool:
    prompt_low = prompt.casefold()
    terms = [
        str(term).casefold()
        for term in candidate.get("trigger_terms") or []
        if len(str(term).strip()) >= 4
    ]
    if any(term and term in prompt_low for term in terms):
        return True
    for ref in candidate.get("affected_scope", {}).get("files") or []:
        path = str(ref.get("path") or "").casefold()
        if path and (path in prompt_low or Path(path).name.casefold() in prompt_low):
            return True
    return False


def source_thickness(candidate: Mapping[str, Any]) -> str:
    explicit = str(candidate.get("source_thickness") or "")
    if explicit in {"thin", "usable", "strong"}:
        return explicit
    refs = candidate.get("source_refs") or []
    if len(refs) >= 3:
        return "strong"
    if len(refs) >= 1:
        return "usable"
    return "thin"


def source_thickness_for_refs(refs: Sequence[Mapping[str, Any]]) -> str:
    if len(refs) >= 3:
        return "strong"
    if refs:
        return "usable"
    return "thin"


def assessment_confidence(*, source_status: str, thickness: str, basis_refs: Sequence[Mapping[str, Any]]) -> float:
    base = {
        "adopted": 0.66,
        "needs_confirmation": 0.44,
        "local_only": 0.40,
        "stale": 0.36,
        "superseded": 0.62,
        "refuted": 0.62,
    }.get(source_status, 0.38)
    base += {"strong": 0.12, "usable": 0.04, "thin": -0.10}.get(thickness, -0.10)
    if len(basis_refs) >= 2:
        base += 0.03
    return round(max(0.0, min(0.95, base)), 4)


def still_rejected_for_assessment(source_status: str) -> str:
    if source_status in {"refuted", "superseded"}:
        return "no"
    # Old source proves the route was rejected then. It does not prove the same
    # route is still invalid now without a read-time source/repo-state basis.
    return "unknown"


def freshness_for_assessment(source_status: str) -> str:
    if source_status in {"refuted", "superseded", "stale", "local_only", "needs_confirmation"}:
        return source_status
    return "unknown"


def proposed_use_for_assessment(
    *,
    source_status: str,
    thickness: str,
    event_type: str,
    action_relevant: bool = True,
) -> str:
    if thickness == "thin":
        return "refresh_sources" if action_relevant else "ask"
    if source_status in {"refuted", "superseded"}:
        return "refresh_sources"
    if source_status in {"needs_confirmation", "local_only", "stale"}:
        return "ask"
    if event_type in {"rejected_route", "do_not_repeat"}:
        return "warn"
    if event_type in {"scope_narrowing", "user_correction"}:
        return "remind"
    return "refresh_sources"


def build_decision_state_assessment(
    candidate: Mapping[str, Any],
    *,
    action_relevant: bool = True,
    as_of: str | None = None,
    basis_refs: Sequence[Mapping[str, Any]] | None = None,
    repo_state_fingerprint: str = "",
) -> dict[str, Any]:
    refs = merge_source_refs(basis_refs or candidate.get("source_refs") or [])
    explicit_thickness = str(candidate.get("source_thickness") or "")
    thickness = explicit_thickness if explicit_thickness in {"thin", "usable", "strong"} else source_thickness_for_refs(refs)
    source_status = str(
        candidate.get("source_review_status")
        or candidate.get("review_status")
        or "needs_confirmation"
    )
    if source_status not in REVIEW_STATUSES:
        source_status = "needs_confirmation"
    event_type = str(candidate.get("event_type") or "")
    proposed_use = proposed_use_for_assessment(
        source_status=source_status,
        thickness=thickness,
        event_type=event_type,
        action_relevant=action_relevant,
    )
    if thickness == "thin" and proposed_use not in THIN_SOURCE_SAFE_USES:
        proposed_use = "refresh_sources"
    decision_id = str(candidate.get("decision_id") or "")
    created_at = as_of or now_utc()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ASSESSMENT_KIND,
        "assessment_id": stable_id(
            "decision_state",
            decision_id,
            source_status,
            thickness,
            proposed_use,
            repo_state_fingerprint,
            length=20,
        ),
        "created_at": created_at,
        "as_of": created_at,
        "assessment_kind": "read_time",
        "decision_event_id": decision_id,
        "basis_refs": refs,
        "repo_state_fingerprint": repo_state_fingerprint,
        "source_review_status": source_status,
        "source_thickness": thickness,
        "still_rejected": still_rejected_for_assessment(source_status),
        "freshness": freshness_for_assessment(source_status),
        "confidence": assessment_confidence(
            source_status=source_status,
            thickness=thickness,
            basis_refs=refs,
        ),
        "proposed_use": proposed_use,
        "truth_boundary": "derived_weather_not_source_fact",
        "terrain_event_mutated": False,
        "policy": {
            "old_source_alone_cannot_assert_still_rejected": True,
            "thin_source_safe_uses": sorted(THIN_SOURCE_SAFE_USES),
        },
    }


def assess_decision_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    prompt: str = "",
) -> list[dict[str, Any]]:
    return [
        build_decision_state_assessment(
            candidate,
            action_relevant=prompt_matches_candidate(prompt, candidate) if prompt else True,
        )
        for candidate in candidates
    ]


def assessment_by_decision_id(
    assessments: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("decision_event_id") or ""): item
        for item in assessments
        if item.get("kind") == ASSESSMENT_KIND and item.get("decision_event_id")
    }


def intervention_level_for_proposed_use(proposed_use: str) -> str:
    if proposed_use == "warn":
        return "warning"
    if proposed_use == "remind":
        return "light_nudge"
    if proposed_use in {"ask", "refresh_sources"}:
        return "state_check"
    return "backstage_only"


def ticket_diagnostic_for_assessment(assessment: Mapping[str, Any]) -> dict[str, Any]:
    proposed_use = str(assessment.get("proposed_use") or "")
    thickness = str(assessment.get("source_thickness") or "thin")
    if thickness == "thin":
        decision = "degraded_to_refresh_sources" if proposed_use == "refresh_sources" else "degraded_to_ask"
    elif proposed_use == "warn":
        decision = "warned"
    elif proposed_use == "remind":
        decision = "nudged"
    elif proposed_use in {"ask", "refresh_sources"}:
        decision = f"degraded_to_{proposed_use}"
    else:
        decision = "backstage_only"
    return {
        "decision": decision,
        "reason": (
            "thin evidence cannot warn"
            if thickness == "thin"
            else "read-time assessment selected safe proposed_use"
        ),
    }


def host_contract_fields_for_ticket(*, proposed_use: str, thickness: str) -> dict[str, Any]:
    annoyance = "high" if proposed_use == "warn" else ("low" if proposed_use in THIN_SOURCE_SAFE_USES else "medium")
    preconditions = [
        "host confirms the ticket source is not already visible",
        "host confirms the active task still matches relevant decisions",
    ]
    if thickness == "thin":
        preconditions.append("host refreshes sources or asks before warning")
    return {
        # Source visibility is runtime context owned by the host. Storing it as
        # a host input marker prevents future agents from treating old storage
        # as proof that the current context is or is not already showing source.
        "source_visibility": "host_runtime_input",
        "annoyance_risk": annoyance,
        "preconditions": preconditions,
        "outcome_feedback_expected": list(TICKET_FEEDBACK_OUTCOMES),
        "host_boundary": {
            "aippocampus_proposes_only": True,
            "host_decides_permission": True,
            "host_decides_priority": True,
            "host_decides_sequence": True,
            "host_decides_safety": True,
        },
    }


def render_coding_continuity_ticket(
    candidates: Sequence[Mapping[str, Any]],
    *,
    prompt: str,
    trigger: str = "compaction_loss",
    visible_context_has_source: bool = False,
    limit: int = 1,
    assessments: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if trigger not in TICKET_TRIGGERS or visible_context_has_source:
        return []
    tickets: list[dict[str, Any]] = []
    assessment_lookup = assessment_by_decision_id(assessments or [])
    for candidate in candidates:
        if str(candidate.get("event_type") or "") not in SURFACEABLE_EVENT_TYPES:
            continue
        action_relevant = prompt_matches_candidate(prompt, candidate)
        decision_id = str(candidate.get("decision_id") or "")
        assessment = dict(
            assessment_lookup.get(decision_id)
            or build_decision_state_assessment(candidate, action_relevant=action_relevant)
        )
        source_status = str(assessment.get("source_review_status") or "")
        proposed_use = str(assessment.get("proposed_use") or "")
        if source_status in {"refuted", "superseded", "stale", "local_only"}:
            continue
        if source_status not in SURFACEABLE_STATUSES and proposed_use not in THIN_SOURCE_SAFE_USES:
            continue
        gate_candidate = {
            "kind": ADJUDICATION_KIND,
            "activation_event_id": decision_id,
            "adjudication_status": "valid_ignored",
            "route": route_for_adjudication("valid_ignored"),
        }
        if not should_surface_candidate(
            gate_candidate,
            context_state="horizon_lost" if trigger == "compaction_loss" else "post_compaction",
            action_relevant=action_relevant,
            visible_context_has_source=visible_context_has_source,
        ):
            continue
        intervention_level = intervention_level_for_proposed_use(proposed_use)
        tickets.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": TICKET_KIND,
                "ticket_id": stable_id("coding_ticket", trigger, prompt, decision_id, length=20),
                "trigger": trigger,
                "intervention_level": intervention_level,
                "relevant_decisions": [decision_id],
                "do_not_repeat": [
                    item.get("path")
                    for item in candidate.get("rejected_paths") or []
                    if isinstance(item, Mapping) and item.get("path")
                ],
                "proposed_use": proposed_use,
                "evidence_refs": assessment.get("basis_refs") or [],
                "basis_refs": assessment.get("basis_refs") or [],
                "source_thickness": assessment.get("source_thickness"),
                "derived_assessment": assessment,
                "expires_at": "task_or_topic_epoch_end",
                "summary": candidate.get("summary"),
                "truth_status": candidate.get("truth_status"),
                "formal_memory_promoted": False,
                "diagnostics": ticket_diagnostic_for_assessment(assessment),
                **host_contract_fields_for_ticket(
                    proposed_use=proposed_use,
                    thickness=str(assessment.get("source_thickness") or "thin"),
                ),
            }
        )
        if len(tickets) >= limit:
            break
    return tickets


def append_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if row.get("kind") != DECISION_KIND:
                raise ValueError(f"unsupported coding decision row kind: {row.get('kind')}")
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def run_extraction(
    *,
    messages_path: Path,
    output_path: Path | None = None,
    thread_key: str | None = None,
    workspace: str | None = None,
    no_write: bool = False,
    ticket_prompt: str = "",
    ticket_trigger: str = "compaction_loss",
    visible_context_has_source: bool = False,
) -> dict[str, Any]:
    messages = iter_jsonl(messages_path)
    candidates = review_decision_candidates(
        extract_decision_candidates(messages, thread_key=thread_key, workspace=workspace)
    )
    assessments = assess_decision_candidates(candidates, prompt=ticket_prompt)
    wrote_count = 0
    if output_path and not no_write and candidates:
        wrote_count = append_rows(output_path, candidates)
    tickets = (
        render_coding_continuity_ticket(
            candidates,
            prompt=ticket_prompt,
            trigger=ticket_trigger,
            visible_context_has_source=visible_context_has_source,
            assessments=assessments,
        )
        if ticket_prompt
        else []
    )
    return {
        "ok": True,
        "kind": "aippocampus_coding_decision_events_run",
        "schema_version": SCHEMA_VERSION,
        "messages_input": str(messages_path),
        "output": str(output_path) if output_path else None,
        "message_count": len(messages),
        "candidate_count": len(candidates),
        "assessment_count": len(assessments),
        "wrote_count": wrote_count,
        "ticket_count": len(tickets),
        "candidates": candidates,
        "assessments": assessments,
        "tickets": tickets,
        "cannot_claim": [
            "complete_design_intent_extraction",
            "global_validity_for_branch_local_decisions",
            "host_agent_intervention_timing",
            "formal_memory_promotion",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages-input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--thread-key")
    parser.add_argument("--workspace")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--ticket-prompt", default="")
    parser.add_argument("--ticket-trigger", choices=TICKET_TRIGGERS, default="compaction_loss")
    parser.add_argument("--visible-context-has-source", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        result = run_extraction(
            messages_path=Path(args.messages_input).resolve(),
            output_path=Path(args.output).resolve() if args.output else None,
            thread_key=args.thread_key,
            workspace=args.workspace,
            no_write=args.no_write,
            ticket_prompt=args.ticket_prompt,
            ticket_trigger=args.ticket_trigger,
            visible_context_has_source=args.visible_context_has_source,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"messages: {result['message_count']}")
        print(f"decision candidates: {result['candidate_count']}")
        print(f"tickets: {result['ticket_count']}")
        if args.output:
            print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
