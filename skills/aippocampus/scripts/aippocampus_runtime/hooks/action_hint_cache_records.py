"""Provider adapters for prepared action-hint cache records."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
RECORD_KIND = "aippocampus_action_hint_prepared_record"
CACHE_KIND = "aippocampus_action_hint_prepared_cache"
DEFAULT_TTL_SECONDS = 14 * 24 * 60 * 60
BLOCKED_STATES = {
    "blocked",
    "private",
    "refuted",
    "rejected",
    "stale",
    "superseded",
    "unsupported",
}
WEAK_SUPPORT_LEVELS = {"scent", "candidate", "dream", "direction_only"}


def _stable_id(*parts: Any) -> str:
    text = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _terms(*values: Any) -> list[str]:
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            tokens.update(_terms(*value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            tokens.update(_terms(*value))
            continue
        for token in re.split(r"[^a-zA-Z0-9]+", str(value or "").casefold()):
            if token:
                tokens.add(token)
    return sorted(tokens)


def _strings(values: Any, *, limit: int = 8) -> list[str]:
    if isinstance(values, str):
        raw = [values]
    elif isinstance(values, (list, tuple, set)):
        raw = list(values)
    else:
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _source_refs(values: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for value in values if isinstance(values, (list, tuple)) else []:
        if isinstance(value, Mapping):
            source_id = str(
                value.get("source_id")
                or value.get("ref_id")
                or value.get("source_ref")
                or value.get("path")
                or ""
            ).strip()
            segment_id = str(
                value.get("segment_id") or value.get("message_id") or value.get("turn_id") or ""
            ).strip()
            if source_id or segment_id:
                refs.append(
                    {
                        key: ref_value
                        for key, ref_value in {
                            "source_id": source_id,
                            "segment_id": segment_id,
                            "turn_id": str(value.get("turn_id") or "").strip(),
                        }.items()
                        if ref_value
                    }
                )
        elif isinstance(value, str) and value.strip():
            refs.append({"source_id": value.strip()})
    return refs[:6]


def _source_handles(values: Any) -> list[dict[str, Any]]:
    handles: list[dict[str, Any]] = []
    for value in values if isinstance(values, (list, tuple)) else []:
        if not isinstance(value, Mapping):
            continue
        handle: dict[str, Any] = {
            key: str(value.get(key) or "").strip()
            for key in ("route_id", "lock_id", "source_id", "segment_id", "deepen_route_id")
            if str(value.get(key) or "").strip()
        }
        if handle:
            handle["reopen_required"] = bool(value.get("reopen_required", True))
            handles.append(handle)
    return handles[:4]


def _freshness(row: Mapping[str, Any]) -> str:
    raw_metadata = row.get("route_metadata")
    metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, Mapping) else {}
    privacy = str(row.get("privacy") or metadata.get("privacy") or "").casefold()
    if privacy in {"private", "blocked"}:
        return privacy
    status = str(row.get("status") or row.get("review_status") or "").casefold()
    if status in BLOCKED_STATES:
        return status
    currentness = str(row.get("freshness") or metadata.get("currentness") or "current").casefold()
    if currentness in BLOCKED_STATES:
        return currentness
    conflict = str(metadata.get("conflict") or row.get("conflict") or "").casefold()
    if conflict in {"refuted", "superseded"}:
        return conflict
    return currentness or "current"


def _expires_at(row: Mapping[str, Any], *, now_unix: float, ttl_seconds: int) -> float:
    try:
        value = float(row.get("expires_at_unix") or row.get("expires_at") or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value
    try:
        created = float(row.get("created_at_unix") or 0)
    except (TypeError, ValueError):
        created = 0.0
    return (created or now_unix) + ttl_seconds


def _base_record(
    *,
    provider_family: str,
    record_id: str,
    action_hint_kind: str,
    next_action: str,
    row: Mapping[str, Any],
    source_refs: Sequence[Mapping[str, Any]],
    source_handles: Sequence[Mapping[str, Any]],
    match_terms: Sequence[Any],
    now_unix: float,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any] | None:
    freshness = _freshness(row)
    if freshness in BLOCKED_STATES or (not source_refs and not source_handles):
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECORD_KIND,
        "record_id": record_id,
        "guidance_id": str(
            row.get("guidance_id")
            or row.get("lesson_id")
            or row.get("clause_id")
            or record_id
        ),
        "guidance_lifecycle_stage": str(row.get("guidance_lifecycle_stage") or "prepared"),
        "review_status": str(row.get("review_status") or row.get("review_state") or ""),
        "provider_family": provider_family,
        "action_hint_kind": action_hint_kind,
        "next_action": next_action,
        "navigation_only": True,
        "no_claim_before_reopen": True,
        "source_reopen_required": True,
        "can_support_factual_claim": False,
        "authority": "navigation_only",
        "scope": str(row.get("scope") or ""),
        "target_fingerprint": str(row.get("target_fingerprint") or ""),
        "path_category_fingerprint": str(row.get("path_category_fingerprint") or ""),
        "workspace_or_environment_profile": str(row.get("workspace_or_environment_profile") or ""),
        "transferability": str(row.get("transferability") or ""),
        "requires_applicability_match": bool(
            row.get("target_fingerprint")
            or row.get("path_category_fingerprint")
            or str(row.get("scope") or "").casefold().startswith(("project:", "machine:"))
        ),
        "does_not_apply_when": _strings(row.get("does_not_apply_when")),
        "topic_epoch": str(row.get("topic_epoch") or ""),
        "freshness": freshness,
        "expires_at_unix": _expires_at(row, now_unix=now_unix, ttl_seconds=ttl_seconds),
        "confidence": str(row.get("confidence") or "medium").casefold(),
        "occurrence_count": int(row.get("occurrence_count") or 1),
        "effectiveness_status": str(row.get("effectiveness_status") or ""),
        "navigation_priority_delta": float(row.get("navigation_priority_delta") or 0.0),
        "source_refs": [dict(ref) for ref in source_refs][:6],
        "source_handles": [dict(handle) for handle in source_handles][:4],
        "anti_nag_ids": _strings(row.get("anti_nag_ids") or [record_id]),
        "active_recall_lock_ids": _strings(row.get("active_recall_locks") or row.get("lock_id")),
        "tool_names": _strings(row.get("tool_names") or row.get("tool_name")),
        "issue_ids": _strings(row.get("issue_ids")),
        "path_terms": _terms(row.get("path_terms")),
        "command_terms": _terms(row.get("command_terms")),
        "risk_modes": _strings(row.get("risk_modes") or row.get("risk")),
        "action_class": str(row.get("action_class") or ""),
        "support_levels": _strings(row.get("support_levels") or WEAK_SUPPORT_LEVELS),
        "match_terms": _terms(match_terms, row.get("reason_codes"), next_action, action_hint_kind),
        "reason_codes": _strings(row.get("reason_codes")),
        "privacy_boundary": {
            "raw_prompt_stored": False,
            "raw_command_text_stored": False,
            "raw_tool_args_stored": False,
            "local_paths_stored": False,
            "model_reasoning_stored": False,
        },
    }


def records_from_aar_v2(
    records: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in records or []:
        refs = _source_refs(row.get("source_refs"))
        record = _base_record(
            provider_family="aar_v2",
            record_id=str(row.get("record_id") or _stable_id("aar_v2", row)),
            action_hint_kind="reopen_source_before_claim",
            next_action=str(
                (row.get("nudge") or {}).get("recommended_action")
                if isinstance(row.get("nudge"), Mapping)
                else ""
            )
            or "reopen_source_before_specific_claim",
            row={**dict(row), "support_levels": WEAK_SUPPORT_LEVELS},
            source_refs=refs,
            source_handles=[],
            match_terms=["source", "claim", "memory", row.get("action_class")],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def records_from_learning_guidance(
    rows: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        next_action = str(row.get("next_action") or "reopen_source_before_action")
        record = _base_record(
            provider_family="learning_loop",
            record_id=str(row.get("guidance_id") or _stable_id("learning_loop", row)),
            action_hint_kind=next_action,
            next_action=next_action,
            row={**dict(row), "command_terms": ["test", "pytest", "ruff", "mypy", "preflight"]},
            source_refs=_source_refs(row.get("source_refs")),
            source_handles=_source_handles(row.get("source_handles")),
            match_terms=[next_action, row.get("guidance_text"), row.get("title")],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def records_from_active_recall_locks(
    rows: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        lock_id = str(row.get("lock_id") or "").strip()
        if not lock_id:
            continue
        handles = [{"lock_id": lock_id, "reopen_required": True}]
        record = _base_record(
            provider_family="active_recall_lock",
            record_id=str(row.get("record_id") or _stable_id("active_lock", lock_id)),
            action_hint_kind=str(row.get("action_hint_kind") or "capture_evidence_before_action"),
            next_action=str(row.get("next_action") or "capture_evidence_before_action"),
            row={**dict(row), "active_recall_locks": [lock_id]},
            source_refs=_source_refs(row.get("source_refs") or row.get("candidate_refs")),
            source_handles=handles,
            match_terms=[row.get("route_reasons"), row.get("aliases"), row.get("next_action")],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def records_from_attention_route_tokens(
    rows: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows or []:
        raw_features = row.get("route_features")
        features: Mapping[str, Any] = raw_features if isinstance(raw_features, Mapping) else {}
        handles = _source_handles(row.get("source_handles"))
        refs = [
            {"source_id": handle.get("source_id"), "segment_id": handle.get("segment_id")}
            for handle in handles
            if handle.get("source_id") or handle.get("segment_id")
        ]
        record = _base_record(
            provider_family="attention_route_token",
            record_id=str(row.get("token_id") or _stable_id("attention_route", row)),
            action_hint_kind=str(row.get("action_hint_kind") or "reopen_route_before_action"),
            next_action=str(row.get("next_action") or "reopen_route_before_action"),
            row=row,
            source_refs=refs,
            source_handles=handles,
            match_terms=[features.get("terms"), row.get("route_token_level")],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def records_from_aippo_learned_clauses(
    clauses: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for clause in clauses or []:
        lifecycle_raw = clause.get("lifecycle")
        activation_raw = clause.get("activation")
        support_raw = clause.get("support")
        lifecycle: Mapping[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, Mapping) else {}
        activation: Mapping[str, Any] = activation_raw if isinstance(activation_raw, Mapping) else {}
        support: Mapping[str, Any] = support_raw if isinstance(support_raw, Mapping) else {}
        if lifecycle.get("status") != "ripe" or not activation.get("foreground_eligible"):
            continue
        next_action = str(
            clause.get("next_action")
            or activation.get("next_action")
            or "reopen_source_before_action"
        )
        record = _base_record(
            provider_family="aippo_learned_clause",
            record_id=str(clause.get("clause_id") or _stable_id("aippo_clause", clause)),
            action_hint_kind="aippo_reopen_first_working_contract",
            next_action=next_action,
            row={
                **dict(clause),
                "confidence": "high" if int(support.get("source_ref_count") or 0) >= 2 else "medium",
                "occurrence_count": max(1, int(support.get("source_ref_count") or 1)),
                "command_terms": [clause.get("kind"), clause.get("guidance"), clause.get("applies_when")],
                "support_levels": WEAK_SUPPORT_LEVELS,
                "reason_codes": [
                    "aippo_learned_clause_provider",
                    "source_reopen_required",
                    *[str(code) for code in clause.get("reason_codes") or []],
                ],
            },
            source_refs=_source_refs(clause.get("source_refs")),
            source_handles=[
                {"deepen_route_id": f"deepen:{clause.get('clause_id')}", "reopen_required": True}
            ],
            match_terms=[clause.get("guidance"), clause.get("applies_when"), clause.get("kind"), next_action],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def records_from_aippo_verification_probes(
    probes: Iterable[Mapping[str, Any]] | None,
    *,
    now_unix: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for probe in probes or []:
        if str(probe.get("status") or probe.get("freshness") or "current").casefold() in BLOCKED_STATES:
            continue
        if str(probe.get("privacy") or "").casefold() in {"private", "local", "blocked"}:
            continue
        next_action = str(probe.get("next_action") or "reopen_probe_source_before_action")
        record = _base_record(
            provider_family="aippo_verification_probe",
            record_id=str(probe.get("probe_id") or _stable_id("aippo_probe", probe)),
            action_hint_kind="aippo_probe_reopen_before_action",
            next_action=next_action,
            row={
                **dict(probe),
                "confidence": str(probe.get("confidence") or "medium"),
                "occurrence_count": max(1, int(probe.get("source_ref_count") or 1)),
                "command_terms": [
                    probe.get("probe_kind"),
                    probe.get("question"),
                    probe.get("guidance"),
                    next_action,
                ],
                "support_levels": WEAK_SUPPORT_LEVELS,
                "reason_codes": [
                    "aippo_verification_probe_provider",
                    "source_reopen_required",
                    *[str(code) for code in probe.get("reason_codes") or []],
                ],
            },
            source_refs=_source_refs(probe.get("source_refs")),
            source_handles=_source_handles(probe.get("source_handles")),
            match_terms=[probe.get("question"), probe.get("guidance"), next_action],
            now_unix=now_unix,
        )
        if record:
            out.append(record)
    return out


def build_action_hint_cache_report(
    *,
    aar_v2_records: Iterable[Mapping[str, Any]] | None = None,
    learning_guidance: Iterable[Mapping[str, Any]] | None = None,
    aippo_learned_clauses: Iterable[Mapping[str, Any]] | None = None,
    aippo_verification_probes: Iterable[Mapping[str, Any]] | None = None,
    active_recall_locks: Iterable[Mapping[str, Any]] | None = None,
    attention_route_tokens: Iterable[Mapping[str, Any]] | None = None,
    now_unix: float | None = None,
) -> dict[str, Any]:
    now_value = float(now_unix if now_unix is not None else time.time())
    records = [
        *records_from_aar_v2(aar_v2_records, now_unix=now_value),
        *records_from_learning_guidance(learning_guidance, now_unix=now_value),
        *records_from_aippo_learned_clauses(aippo_learned_clauses, now_unix=now_value),
        *records_from_aippo_verification_probes(aippo_verification_probes, now_unix=now_value),
        *records_from_active_recall_locks(active_recall_locks, now_unix=now_value),
        *records_from_attention_route_tokens(attention_route_tokens, now_unix=now_value),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CACHE_KIND,
        "record_count": len(records),
        "records": records,
        "provider_counts": {
            provider: sum(1 for row in records if row["provider_family"] == provider)
            for provider in sorted({row["provider_family"] for row in records})
        },
        "missing_provider_count": sum(
            1
            for provider_rows in (
                aar_v2_records,
                learning_guidance,
                aippo_learned_clauses,
                aippo_verification_probes,
                active_recall_locks,
                attention_route_tokens,
            )
            if provider_rows is None
        ),
        "privacy_boundary": {
            "raw_prompts_serialized": False,
            "raw_tool_args_serialized": False,
            "raw_command_text_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
        },
    }
