#!/usr/bin/env python3
"""Source-trailed continuity domain substrate.

Continuity domains are navigation structure, not clean source. They preserve a
durable interpretation trail over clean source refs so later agents can reopen
the right material instead of rebuilding long-running context from scattered
search hits. Keep this module append-only and pointer-first: hook output may
carry compact domain pointers, while exact or public claims still reopen clean
source.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import artifact_lease
from aippocampus_runtime.core import (
    compact_text,
    default_thread_store_dir,
    now_utc,
    sanitize_external_model_text,
)
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.authority import (
    ACTION_DIRECTION_ONLY,
    ACTION_IGNORE_OR_BLOCKED,
    ACTION_REOPENABLE_ROUTE,
    TRUST_IGNORE,
    TRUST_SEMANTIC_HINT,
    TRUST_SOURCE_REQUIRED,
    action_grammar_for_level,
    trust_contract_for_level,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.source.search import iter_clean_messages

CONTINUITY_DOMAIN_SCHEMA_VERSION = 1
CONTINUITY_DOMAIN_EVENT_KIND = "aippocampus_continuity_domain_event"
CONTINUITY_DOMAIN_SNAPSHOT_KIND = "aippocampus_continuity_domains_snapshot"
CONTINUITY_DOMAIN_POINTER_KIND = "continuity_domain_pointer"
CONTINUITY_DOMAIN_DEEPEN_KIND = "aippocampus_continuity_domain_deepen"
SITUATION_GLYPH_KIND = "aippocampus_situation_glyph"

EVENT_LOG_FILENAME = "continuity-domain-events.jsonl"
SNAPSHOT_DIR_NAME = "continuity-domain-snapshots"
LATEST_POINTER_NAME = "latest.json"
LEASE_NAME = ".continuity-domains.lock"
DEFAULT_DOMAIN_HANDLE_TTL_SECONDS = 30 * 60

DOMAIN_EVENT_KINDS = {
    "domain_created",
    "support_source_added",
    "counter_source_added",
    "correction_source_added",
    "representative_source_added",
    "boundary_pinned",
    "domain_reinterpreted",
    "domain_split",
    "domain_merged",
    "domain_superseded",
    "domain_retired",
}
PATHLET_EVENT_KINDS = {
    "pathlet_created",
    "pathlet_reinterpreted",
    "pathlet_superseded",
    "pathlet_retired",
}
ACCEPTED_EVENT_KINDS = DOMAIN_EVENT_KINDS | PATHLET_EVENT_KINDS

DOMAIN_STATUSES = {"active", "contested", "stale", "blocked", "superseded", "retired"}
BOUNDARY_EFFECTS = {
    "block_hook",
    "require_source_reopen",
    "block_public_claim",
    "suppress_domain",
    "supersede_prior_conclusion",
    "redirect",
}
HARD_BLOCKING_BOUNDARY_EFFECTS = {"block_hook", "suppress_domain"}
REOPEN_BOUNDARY_EFFECTS = {
    "require_source_reopen",
    "block_public_claim",
    "supersede_prior_conclusion",
    "redirect",
}
DERIVED_ONLY_STATUS = "derived_only_not_runtime_writable"
REDACTION_MARKERS = (
    "<local-path-redacted>",
    "<sensitive-value-redacted>",
    "<redacted:",
)

SIGNAL_PRODUCERS = {
    "source_texture",
    "dream",
    "journey",
    "hexagram",
    "cognitive_map",
    "navigation_potential",
    "working_memory",
    "continuity_domain",
}
SIGNAL_PRODUCER_BOUNDARIES = {
    "dream": "dream_hypothesis_not_source_fact",
    "hexagram": "hexagram_atmosphere_not_fact",
    "cognitive_map": "cognitive_map_route_not_source_fact",
    "journey": "journey_route_not_source_fact",
    "source_texture": "texture_signal_not_source_fact",
    "navigation_potential": "navigation_not_truth",
    "working_memory": "working_memory_candidate_not_source_fact",
    "continuity_domain": "domain_pointer_not_source_fact",
}

TEXT_FIELDS = (
    "title",
    "summary",
    "working_conclusion_short",
    "why_it_may_matter",
    "why_it_may_matter_now",
    "detail",
    "signal_detail",
)


def _stable_id(*parts: Any, prefix: str, length: int = 20) -> str:
    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _fingerprint_paths(paths: Sequence[Path]) -> str:
    parts: list[str] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            parts.append(f"{path.name}:missing")
            continue
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return _stable_id(*parts, prefix="source")


def clean_source_fingerprint(clean_source_dir: Path) -> str:
    return _fingerprint_paths([clean_source_dir / "messages.jsonl", clean_source_dir / "turns.jsonl"])


def continuity_domain_snapshot_fingerprint(
    *,
    snapshot_path: Path | None,
    clean_source_dir: Path | None = None,
) -> str:
    paths: list[Path] = []
    if clean_source_dir is not None:
        paths.extend([clean_source_dir / "messages.jsonl", clean_source_dir / "turns.jsonl"])
    if snapshot_path is not None:
        paths.append(snapshot_path)
    return _fingerprint_paths(paths)


def _safe_text(value: Any, chars: int = 220) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    payload = redact_sensitive_values(redact_private_paths(sanitized))
    return compact_text(str(payload or ""), chars)


def _safe_list(values: Any, *, limit: int = 12, chars: int = 80) -> list[str]:
    if not isinstance(values, (list, tuple)):
        values = [values] if values not in (None, "") else []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _safe_text(value, chars).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def default_continuity_domain_events_path(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    return (
        default_thread_store_dir(cwd, rollout, registry_dir=registry_dir)
        / "clean-source"
        / EVENT_LOG_FILENAME
    )


def default_continuity_domain_snapshot_dir(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    return default_thread_store_dir(cwd, rollout, registry_dir=registry_dir) / SNAPSHOT_DIR_NAME


def default_continuity_domains_latest_path(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    return default_continuity_domain_snapshot_dir(
        cwd,
        rollout=rollout,
        registry_dir=registry_dir,
    ) / LATEST_POINTER_NAME


def continuity_domains_latest_path_for_clean_source(clean_source_dir: Path) -> Path:
    return clean_source_dir.resolve().parent / SNAPSHOT_DIR_NAME / LATEST_POINTER_NAME


def _ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(ref.get("thread_key") or ""),
        str(ref.get("source_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ref.get("turn_index") or ""),
        str(ref.get("line") or ref.get("source_line") or ""),
    )


def _dedupe_refs(refs: Iterable[dict[str, Any]], *, limit: int = 24) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for ref in refs:
        key = _ref_key(ref)
        if key in seen or not any(key):
            continue
        seen.add(key)
        out.append(ref)
        if len(out) >= limit:
            break
    return out


def _message_matches_ref(message: Mapping[str, Any], ref: Mapping[str, Any]) -> bool:
    if ref.get("message_id") and str(message.get("message_id") or message.get("id") or "") == str(
        ref.get("message_id")
    ):
        return True
    if ref.get("turn_id") and str(message.get("turn_id") or "") == str(ref.get("turn_id")):
        return True
    if ref.get("turn_index") and str(message.get("turn_index") or "") == str(
        ref.get("turn_index")
    ):
        return True
    if ref.get("line") and str(message.get("source_line") or "") == str(ref.get("line")):
        return True
    return False


def _filter_resolving_refs(
    refs: Iterable[dict[str, Any]],
    *,
    clean_source_dir: Path | None,
) -> list[dict[str, Any]]:
    clean = _dedupe_refs(safe_source_refs(list(refs)), limit=24)
    if clean_source_dir is None:
        return clean
    messages_path = clean_source_dir / "messages.jsonl"
    if not messages_path.exists():
        return []
    messages = list(iter_clean_messages(messages_path))
    return [ref for ref in clean if any(_message_matches_ref(message, ref) for message in messages)]


def _normalize_source_refs(
    row: Mapping[str, Any],
    *,
    clean_source_dir: Path | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key in (
        "source_refs",
        "support_refs",
        "counter_refs",
        "correction_refs",
        "boundary_refs",
        "representative_refs",
        "ordered_source_refs",
    ):
        refs.extend(safe_source_refs(row.get(key)))
    return _filter_resolving_refs(refs, clean_source_dir=clean_source_dir)


def _source_ref_groups(
    row: Mapping[str, Any],
    *,
    clean_source_dir: Path | None,
) -> dict[str, list[dict[str, Any]]]:
    groups = {
        "support_refs": safe_source_refs(row.get("support_refs") or row.get("source_refs")),
        "counter_refs": safe_source_refs(row.get("counter_refs")),
        "correction_refs": safe_source_refs(row.get("correction_refs")),
        "boundary_refs": safe_source_refs(row.get("boundary_refs")),
        "representative_refs": safe_source_refs(row.get("representative_refs")),
    }
    if clean_source_dir is None:
        return {key: _dedupe_refs(value, limit=24) for key, value in groups.items()}
    return {
        key: _filter_resolving_refs(value, clean_source_dir=clean_source_dir)
        for key, value in groups.items()
    }


def normalize_continuity_domain_event(
    row: Mapping[str, Any],
    *,
    clean_source_dir: Path | None = None,
) -> dict[str, Any] | None:
    event_kind = _safe_text(row.get("event_kind") or row.get("kind"), 80)
    if event_kind == CONTINUITY_DOMAIN_EVENT_KIND:
        event_kind = _safe_text(row.get("domain_event_kind"), 80)
    if event_kind not in ACCEPTED_EVENT_KINDS:
        return None
    source_refs = _normalize_source_refs(row, clean_source_dir=clean_source_dir)
    if not source_refs:
        return None
    domain_id = _safe_text(row.get("domain_id"), 100)
    pathlet_id = _safe_text(row.get("pathlet_id"), 100)
    title = _safe_text(row.get("title") or domain_id or pathlet_id, 160)
    if event_kind in DOMAIN_EVENT_KINDS and not domain_id:
        domain_id = _stable_id(title, source_refs, prefix="cd")
    if event_kind in PATHLET_EVENT_KINDS and not pathlet_id:
        pathlet_id = _stable_id(title, source_refs, prefix="pathlet")
    source_groups = _source_ref_groups(row, clean_source_dir=clean_source_dir)
    event_id = _safe_text(row.get("event_id"), 100) or _stable_id(
        event_kind,
        domain_id,
        pathlet_id,
        title,
        source_refs,
        row.get("created_at") or row.get("timestamp"),
        prefix="cde",
    )
    event: dict[str, Any] = {
        "kind": CONTINUITY_DOMAIN_EVENT_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "event_id": event_id,
        "event_kind": event_kind,
        "created_at": _safe_text(row.get("created_at") or row.get("timestamp") or now_utc(), 80),
        "source_refs": source_refs,
        "source_ref_count": len(source_refs),
    }
    if domain_id:
        event["domain_id"] = domain_id
    if pathlet_id:
        event["pathlet_id"] = pathlet_id
    for key in TEXT_FIELDS:
        if row.get(key) not in (None, ""):
            event[key] = _safe_text(row.get(key), 260)
    for key in ("domain_type", "scale", "status", "effect", "strength", "boundary_kind"):
        if row.get(key) not in (None, ""):
            event[key] = _safe_text(row.get(key), 80)
    for key in ("activation_cues", "negative_cues", "scope_labels", "long_range_tendencies"):
        values = _safe_list(row.get(key), limit=16, chars=100)
        if values:
            event[key] = values
    for key, refs in source_groups.items():
        if refs:
            event[key] = refs
    ordered_refs = _filter_resolving_refs(
        safe_source_refs(row.get("ordered_source_refs") or row.get("source_refs")),
        clean_source_dir=clean_source_dir,
    )
    if ordered_refs:
        event["ordered_source_refs"] = ordered_refs
    if row.get("parent_domain_ids") is not None:
        event["parent_domain_ids"] = _safe_list(row.get("parent_domain_ids"), limit=12)
    if row.get("merged_from") is not None:
        event["merged_from"] = _safe_list(row.get("merged_from"), limit=12)
    if row.get("split_from") is not None:
        event["split_from"] = _safe_text(row.get("split_from"), 100)
    if row.get("supersedes") is not None:
        event["supersedes"] = _safe_list(row.get("supersedes"), limit=12)
    if row.get("superseded_by") is not None:
        event["superseded_by"] = _safe_text(row.get("superseded_by"), 100)
    payload = redact_sensitive_values(redact_private_paths(event))
    return payload if isinstance(payload, dict) else event


def load_continuity_domain_events(
    path: Path,
    *,
    clean_source_dir: Path | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in iter_jsonl(path):
        normalized = normalize_continuity_domain_event(row, clean_source_dir=clean_source_dir)
        if normalized:
            events.append(normalized)
    return events


def append_continuity_domain_event(
    path: Path,
    event: Mapping[str, Any],
    *,
    clean_source_dir: Path | None = None,
    wait_timeout_seconds: float = 0.0,
) -> dict[str, Any]:
    normalized = normalize_continuity_domain_event(event, clean_source_dir=clean_source_dir)
    if normalized is None:
        raise ValueError("continuity domain events require a supported event_kind and source refs")
    path.parent.mkdir(parents=True, exist_ok=True)
    with artifact_lease(
        path.parent,
        LEASE_NAME,
        wait_timeout_seconds=wait_timeout_seconds,
    ):
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(normalized, ensure_ascii=False, sort_keys=True) + "\n")
    return normalized


def _empty_domain(domain_id: str) -> dict[str, Any]:
    return {
        "domain_id": domain_id,
        "domain_type": "recurring_question",
        "scale": "meso",
        "title": domain_id,
        "working_conclusion_short": "",
        "scope_labels": [],
        "activation_cues": [],
        "negative_cues": [],
        "long_range_tendencies": [],
        "evidence_trail": {
            "support_refs": [],
            "counter_refs": [],
            "correction_refs": [],
            "boundary_refs": [],
            "representative_refs": [],
        },
        "pinned_boundary_conditions": [],
        "lineage": {
            "event_ids": [],
            "version": 0,
            "parent_domain_ids": [],
            "merged_from": [],
            "split_from": None,
            "supersedes": [],
            "superseded_by": None,
        },
        "lifecycle": {
            "status": "active",
            "last_reinterpreted_at": None,
            "review_after": None,
            "expires_at": None,
            "invalidation_triggers": [
                "new_counter_source",
                "explicit_user_correction",
                "source_generation_changed",
                "public_claim_requested",
            ],
        },
        "activation": {
            "hook_policy": "pointer_only",
            "default_visibility": "private_local",
            "foreground_projection": "domain_pointer",
        },
    }


def _merge_refs(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_refs([*existing, *incoming], limit=48)


def _apply_event_to_domain(domain: dict[str, Any], event: Mapping[str, Any]) -> None:
    domain["lineage"]["event_ids"].append(event.get("event_id"))
    domain["lineage"]["version"] = int(domain["lineage"].get("version") or 0) + 1
    for key in ("title", "working_conclusion_short", "domain_type", "scale"):
        if event.get(key):
            domain[key] = event[key]
    for key in ("activation_cues", "negative_cues", "scope_labels", "long_range_tendencies"):
        domain[key] = _safe_list([*domain.get(key, []), *event.get(key, [])], limit=24)
    trail = domain["evidence_trail"]
    event_kind = str(event.get("event_kind") or "")
    if event_kind in {"domain_created", "support_source_added", "domain_reinterpreted"}:
        trail["support_refs"] = _merge_refs(trail["support_refs"], event.get("support_refs") or event.get("source_refs") or [])
    if event_kind == "counter_source_added":
        trail["counter_refs"] = _merge_refs(trail["counter_refs"], event.get("counter_refs") or event.get("source_refs") or [])
    if event_kind == "correction_source_added":
        trail["correction_refs"] = _merge_refs(
            trail["correction_refs"],
            event.get("correction_refs") or event.get("source_refs") or [],
        )
    if event_kind == "representative_source_added":
        trail["representative_refs"] = _merge_refs(
            trail["representative_refs"],
            event.get("representative_refs") or event.get("source_refs") or [],
        )
    if event_kind == "boundary_pinned":
        boundary_refs = event.get("boundary_refs") or event.get("source_refs") or []
        trail["boundary_refs"] = _merge_refs(trail["boundary_refs"], boundary_refs)
        domain["pinned_boundary_conditions"].append(
            {
                "pin_id": event.get("pin_id")
                or _stable_id(event.get("event_id"), event.get("effect"), prefix="pin"),
                "kind": event.get("boundary_kind") or "explicit_user_correction",
                "source_refs": boundary_refs,
                "strength": event.get("strength") or "hard",
                "effect": event.get("effect") or "require_source_reopen",
                "summary": event.get("summary") or event.get("title") or "",
            }
        )
    if event_kind == "domain_reinterpreted":
        domain["lifecycle"]["last_reinterpreted_at"] = event.get("created_at")
    if event_kind == "domain_superseded":
        domain["lifecycle"]["status"] = "superseded"
        if event.get("superseded_by"):
            domain["lineage"]["superseded_by"] = event.get("superseded_by")
    if event_kind == "domain_retired":
        domain["lifecycle"]["status"] = "retired"
    for key in ("parent_domain_ids", "merged_from", "supersedes"):
        if event.get(key):
            domain["lineage"][key] = _safe_list(
                [*domain["lineage"].get(key, []), *event.get(key, [])],
                limit=24,
            )
    if event.get("split_from"):
        domain["lineage"]["split_from"] = event.get("split_from")
    if event.get("status") in DOMAIN_STATUSES:
        domain["lifecycle"]["status"] = event.get("status")


def _finalize_domain(domain: dict[str, Any]) -> dict[str, Any]:
    trail = domain["evidence_trail"]
    if not trail["representative_refs"]:
        trail["representative_refs"] = _dedupe_refs(
            [
                *trail.get("boundary_refs", []),
                *trail.get("correction_refs", []),
                *trail.get("counter_refs", []),
                *trail.get("support_refs", []),
            ],
            limit=6,
        )
    status = str(domain["lifecycle"].get("status") or "active")
    effects = {
        str(boundary.get("effect") or "")
        for boundary in domain.get("pinned_boundary_conditions") or []
        if isinstance(boundary, dict)
    }
    if domain.get("scale") == "macro":
        status = "blocked"
        domain["macro_persistence_state"] = DERIVED_ONLY_STATUS
    if effects & HARD_BLOCKING_BOUNDARY_EFFECTS:
        status = "blocked"
    elif trail.get("counter_refs") and status == "active":
        status = "contested"
    elif effects & REOPEN_BOUNDARY_EFFECTS and status == "active":
        status = "active"
    domain["lifecycle"]["status"] = status
    trust_level = TRUST_SOURCE_REQUIRED
    if status in {"blocked", "stale", "superseded", "retired"}:
        trust_level = TRUST_IGNORE
    surface = {
        "support_level": "source_required" if trust_level == TRUST_SOURCE_REQUIRED else "suppressed",
        "source_refs": trail.get("representative_refs") or trail.get("support_refs"),
        "currentness": "active" if status == "active" else status,
        "reopen_plan": {"status": "ready" if trust_level == TRUST_SOURCE_REQUIRED else "blocked"},
    }
    action = action_grammar_for_level(trust_level, surface)
    domain["claim_contract"] = {
        "trust_level": trust_level,
        "action_grammar": action,
        "trust_contract": trust_contract_for_level(trust_level, surface),
        "scale_does_not_set_authority": True,
        "allowed_claim_classes": [
            "broad_theme",
            "task_route",
            "prior_decision_shape",
        ],
        "requires_reopen_for": [
            "exact_quote",
            "exact_number_or_date",
            "public_claim",
            "code_change",
            "legal_security_medical_money",
            "user_identity_or_private_profile_fact",
            "conflict_or_stale_claim",
        ],
        "cannot_claim": [
            "this_is_exact_wording",
            "this_is_current_after_later_updates",
            "this_is_safe_to_publish",
            "domain_summary_is_source_truth",
        ],
    }
    domain["source_boundary"] = _domain_source_boundary()
    return redact_sensitive_values(redact_private_paths(domain))


def _pathlet_from_event(event: Mapping[str, Any]) -> dict[str, Any]:
    ordered_refs = event.get("ordered_source_refs") or event.get("source_refs") or []
    status = "active"
    event_kind = str(event.get("event_kind") or "")
    if event_kind == "pathlet_retired":
        status = "retired"
    if event_kind == "pathlet_superseded":
        status = "superseded"
    return {
        "pathlet_id": event.get("pathlet_id"),
        "title": event.get("title") or event.get("pathlet_id"),
        "summary": event.get("summary") or "",
        "status": status,
        "ordered_source_refs": ordered_refs,
        "source_refs": _dedupe_refs(ordered_refs, limit=24),
        "scope_labels": event.get("scope_labels") or [],
        "domain_ids": _safe_list(event.get("domain_ids"), limit=12),
        "lineage": {"event_ids": [event.get("event_id")]},
        "truth_boundary": "pathlet_is_ordered_route_not_source_fact",
        "action_grammar": ACTION_REOPENABLE_ROUTE if status == "active" else ACTION_IGNORE_OR_BLOCKED,
    }


def _derive_macro_tendencies(domains: list[dict[str, Any]], pathlets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tendencies: dict[str, dict[str, Any]] = {}
    for domain in domains:
        if domain.get("scale") == "macro":
            continue
        if domain.get("lifecycle", {}).get("status") in {"blocked", "retired", "superseded"}:
            continue
        labels = [
            *domain.get("long_range_tendencies", []),
            *domain.get("scope_labels", []),
        ]
        for label in labels[:8]:
            key = label.casefold()
            row = tendencies.setdefault(
                key,
                {
                    "macro_id": _stable_id(label, prefix="macro"),
                    "kind": "continuity_macro_tendency_pointer",
                    "label": label,
                    "scale": "macro",
                    "persistence_state": DERIVED_ONLY_STATUS,
                    "source_domain_ids": [],
                    "pathlet_ids": [],
                    "source_refs": [],
                    "action_grammar": ACTION_DIRECTION_ONLY,
                    "trust_level": TRUST_SEMANTIC_HINT,
                    "truth_boundary": "macro_tendency_is_derived_pointer_not_runtime_truth",
                },
            )
            row["source_domain_ids"].append(domain.get("domain_id"))
            row["source_refs"] = _dedupe_refs(
                [
                    *row.get("source_refs", []),
                    *(domain.get("evidence_trail", {}).get("representative_refs") or []),
                ],
                limit=8,
            )
    for pathlet in pathlets:
        for label in pathlet.get("scope_labels") or []:
            key = str(label).casefold()
            if key in tendencies:
                tendencies[key]["pathlet_ids"].append(pathlet.get("pathlet_id"))
    return list(tendencies.values())[:12]


def materialize_continuity_domains(
    events: Sequence[Mapping[str, Any]],
    *,
    clean_source_dir: Path | None = None,
) -> dict[str, Any]:
    domains: dict[str, dict[str, Any]] = {}
    pathlets: dict[str, dict[str, Any]] = {}
    accepted = 0
    rejected = 0
    for raw in events:
        event = normalize_continuity_domain_event(raw, clean_source_dir=clean_source_dir)
        if event is None:
            rejected += 1
            continue
        accepted += 1
        event_kind = str(event.get("event_kind") or "")
        if event_kind in DOMAIN_EVENT_KINDS:
            domain_id = str(event.get("domain_id") or "")
            if not domain_id:
                rejected += 1
                accepted -= 1
                continue
            domain = domains.setdefault(domain_id, _empty_domain(domain_id))
            _apply_event_to_domain(domain, event)
        elif event_kind in PATHLET_EVENT_KINDS:
            pathlet_id = str(event.get("pathlet_id") or "")
            if not pathlet_id:
                rejected += 1
                accepted -= 1
                continue
            pathlets[pathlet_id] = _pathlet_from_event(event)
    finalized_domains = [_finalize_domain(domain) for domain in domains.values()]
    finalized_domains.sort(key=lambda item: str(item.get("domain_id") or ""))
    finalized_pathlets = list(pathlets.values())
    finalized_pathlets.sort(key=lambda item: str(item.get("pathlet_id") or ""))
    pinned_boundaries = [
        boundary
        for domain in finalized_domains
        for boundary in domain.get("pinned_boundary_conditions") or []
        if isinstance(boundary, dict)
    ]
    snapshot_id = _stable_id(
        [domain.get("domain_id") for domain in finalized_domains],
        [pathlet.get("pathlet_id") for pathlet in finalized_pathlets],
        accepted,
        prefix="cdsnap",
    )
    snapshot = {
        "kind": CONTINUITY_DOMAIN_SNAPSHOT_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generated_at": now_utc(),
        "domains": finalized_domains,
        "pathlets": finalized_pathlets,
        "pinned_boundaries": pinned_boundaries,
        "macro_tendencies": _derive_macro_tendencies(finalized_domains, finalized_pathlets),
        "source_boundary": _snapshot_source_boundary(),
        "metrics": {
            "event_count": len(events),
            "accepted_event_count": accepted,
            "rejected_event_count": rejected,
            "domain_count": len(finalized_domains),
            "pathlet_count": len(finalized_pathlets),
            "pinned_boundary_count": len(pinned_boundaries),
        },
    }
    return redact_sensitive_values(redact_private_paths(snapshot))


def publish_continuity_domains_snapshot(
    *,
    events_path: Path,
    snapshot_dir: Path,
    clean_source_dir: Path | None = None,
    wait_timeout_seconds: float = 0.0,
) -> dict[str, Any]:
    events = load_continuity_domain_events(events_path, clean_source_dir=clean_source_dir)
    snapshot = materialize_continuity_domains(events, clean_source_dir=clean_source_dir)
    snapshot_id = str(snapshot.get("snapshot_id") or _stable_id(time.time_ns(), prefix="cdsnap"))
    snapshot_path = snapshot_dir / f"{snapshot_id}.json"
    latest_path = snapshot_dir / LATEST_POINTER_NAME
    pointer = {
        "kind": "aippocampus_continuity_domains_latest_pointer",
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "updated_at": snapshot.get("generated_at"),
        "snapshot": snapshot,
    }
    with artifact_lease(
        snapshot_dir,
        LEASE_NAME,
        wait_timeout_seconds=wait_timeout_seconds,
    ):
        _write_json_atomic(snapshot_path, snapshot)
        _write_json_atomic(latest_path, pointer)
    return {
        "kind": "aippocampus_continuity_domains_publish_report",
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "status": "ok",
        "snapshot_id": snapshot_id,
        "metrics": snapshot.get("metrics") or {},
        "source_boundary": _snapshot_source_boundary(),
    }


def load_continuity_domains_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    snapshot = data.get("snapshot") if data.get("snapshot") else data
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("kind") != CONTINUITY_DOMAIN_SNAPSHOT_KIND:
        return None
    return snapshot


def _domain_source_boundary() -> dict[str, Any]:
    return {
        "pointer_only_not_fact": True,
        "domain_summary_not_source": True,
        "source_reopen_required_for_facts": True,
        "hook_default_body_allowed": False,
        "clean_source_is_authority": True,
        "scale_does_not_set_authority": True,
        "macro_tendency_runtime_writes_allowed": False,
    }


def _snapshot_source_boundary() -> dict[str, Any]:
    return {
        "events_are_domain_terrain_not_clean_source": True,
        "snapshot_is_bridge_not_truth_source": True,
        "source_reopen_required_before_claim": True,
        "clean_source_mutation_allowed": False,
        "raw_prompt_serialized": False,
        "raw_source_text_serialized": False,
        "local_paths_serialized": False,
        "sensitive_values_serialized": False,
    }


def continuity_domain_public_safety_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    raw_metrics = snapshot.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    source_ref_count = 0
    suppressed_count = 0
    for domain in snapshot.get("domains") or []:
        if not isinstance(domain, Mapping):
            continue
        raw_trail = domain.get("evidence_trail")
        trail: Mapping[str, Any] = raw_trail if isinstance(raw_trail, Mapping) else {}
        for refs in trail.values():
            if isinstance(refs, list):
                source_ref_count += len(refs)
        raw_lifecycle = domain.get("lifecycle")
        lifecycle: Mapping[str, Any] = (
            raw_lifecycle if isinstance(raw_lifecycle, Mapping) else {}
        )
        if lifecycle.get("status") in {"blocked", "superseded", "retired"}:
            suppressed_count += 1
    encoded_snapshot = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return {
        "kind": "aippocampus_continuity_domain_public_safety_report",
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "navigation_only": True,
        "metrics": {
            "event_count": int(metrics.get("event_count") or 0),
            "snapshot_count": 1 if snapshot else 0,
            "source_ref_count": source_ref_count,
            "redaction_count": sum(encoded_snapshot.count(marker) for marker in REDACTION_MARKERS),
            "suppressed_count": suppressed_count,
        },
        "contract": {
            "events_are_domain_terrain_not_clean_source": True,
            "snapshot_is_bridge_not_truth_source": True,
            "source_reopen_required_before_claim": True,
            "clean_source_mutation_allowed": False,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "sensitive_values_serialized": False,
        },
        "cannot_claim": [
            "domain_event_is_current_truth_without_read_time_assessment",
            "snapshot_replaces_clean_source",
            "navigation_summary_is_source_evidence",
        ],
    }


def continuity_domain_pointer(
    domain: Mapping[str, Any],
    *,
    why_it_may_matter_now: str = "",
    handle: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    raw_contract = domain.get("claim_contract")
    contract: Mapping[str, Any] = (
        raw_contract if isinstance(raw_contract, Mapping) else {}
    )
    trust = str(contract.get("trust_level") or TRUST_SOURCE_REQUIRED)
    action = str(contract.get("action_grammar") or ACTION_REOPENABLE_ROUTE)
    refs = (
        domain.get("evidence_trail", {}).get("representative_refs")
        or domain.get("evidence_trail", {}).get("support_refs")
        or []
    )
    domain_id = str(domain.get("domain_id") or "")
    status = str(domain.get("lifecycle", {}).get("status") or "active")
    pointer = {
        "card_kind": CONTINUITY_DOMAIN_POINTER_KIND,
        "domain_id": domain_id,
        "label": _safe_text(domain.get("title") or domain_id, 120),
        "theme": _safe_text(domain.get("title") or domain_id, 120),
        "domain_type": domain.get("domain_type") or "recurring_question",
        "scale": domain.get("scale") or "meso",
        "status": status,
        "support_level": "source_required" if action == ACTION_REOPENABLE_ROUTE else "suppressed",
        "trust_level": trust,
        "action_grammar": action,
        "trust_contract": contract.get("trust_contract")
        if isinstance(contract.get("trust_contract"), Mapping)
        else trust_contract_for_level(trust),
        "source_refs": safe_source_refs(refs)[:6],
        "representative_sources": safe_source_refs(refs)[:4],
        "counter_sources": safe_source_refs(domain.get("evidence_trail", {}).get("counter_refs"))[:4],
        "pinned_boundary_conditions": [
            {
                "kind": item.get("kind"),
                "strength": item.get("strength"),
                "effect": item.get("effect"),
            }
            for item in domain.get("pinned_boundary_conditions") or []
            if isinstance(item, Mapping)
        ][:4],
        "why_it_may_matter_now": _safe_text(
            why_it_may_matter_now
            or domain.get("why_it_may_matter")
            or "This domain may provide long-running continuity coordinates.",
            180,
        ),
        "suggested_use": "Use as a pointer to continuity; run recall_deepen or reopen clean source before factual claims.",
        "reopen_plan": {
            "status": "ready" if action == ACTION_REOPENABLE_ROUTE and handle else "needs_context",
            "recommended_tool": "recall_deepen" if handle else "recall_context",
            "arguments": {"handle": handle} if handle else {"domain_id": domain_id},
            "manual_query_invention_expected": False,
        },
        "source_boundary": _domain_source_boundary(),
    }
    return redact_sensitive_values(redact_private_paths(pointer))


def continuity_domain_handle(
    domain: Mapping[str, Any],
    *,
    clean_source_dir: Path | None = None,
    snapshot_path: Path | None = None,
    ttl_seconds: int = DEFAULT_DOMAIN_HANDLE_TTL_SECONDS,
) -> dict[str, Any]:
    domain_id = str(domain.get("domain_id") or "")
    refs = (
        domain.get("evidence_trail", {}).get("representative_refs")
        or domain.get("evidence_trail", {}).get("support_refs")
        or []
    )
    now = int(time.time())
    handle: dict[str, Any] = {
        "schema_version": 1,
        "kind": "continuity_domain",
        "domain_id": domain_id,
        "source_refs": safe_source_refs(refs)[:6],
        "snapshot_fingerprint": continuity_domain_snapshot_fingerprint(
            snapshot_path=snapshot_path,
            clean_source_dir=clean_source_dir if clean_source_dir and clean_source_dir.exists() else None,
        ),
        "issued_unix": now,
        "expires_unix": now + max(1, int(ttl_seconds or DEFAULT_DOMAIN_HANDLE_TTL_SECONDS)),
    }
    if clean_source_dir is not None and (clean_source_dir / "messages.jsonl").exists():
        handle["source_fingerprint"] = clean_source_fingerprint(clean_source_dir)
    return redact_sensitive_values(redact_private_paths(handle))


def _terms(text: str) -> set[str]:
    out: set[str] = set()
    for raw in split_query_terms([str(text or "")]):
        token = raw.strip(".,:;!?()[]{}<>\"'`").casefold()
        if len(token) < 2:
            continue
        out.add(token)
        for part in token.replace("#", " #").split():
            clean = part.strip(".,:;!?()[]{}<>\"'`").casefold()
            if len(clean) >= 2:
                out.add(clean)
    return out


def _overlap_score(prompt_terms: set[str], prompt_text: str, domain_terms: set[str], domain_text: str) -> int:
    score = len(prompt_terms & domain_terms)
    prompt_low = prompt_text.casefold()
    domain_low = domain_text.casefold()
    for term in domain_terms:
        if term and term in prompt_low:
            score += 1
    for term in prompt_terms:
        if term and term in domain_low:
            score += 1
    return score


def match_continuity_domain_pointers(
    prompt: str,
    snapshot: Mapping[str, Any] | None,
    *,
    limit: int = 3,
    clean_source_dir: Path | None = None,
    snapshot_path: Path | None = None,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(snapshot, Mapping):
        return []
    prompt_text = str(prompt or "")
    prompt_terms = _terms(prompt_text)
    if not prompt_terms:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for domain in snapshot.get("domains") or []:
        if not isinstance(domain, Mapping):
            continue
        raw_lifecycle = domain.get("lifecycle")
        lifecycle: Mapping[str, Any] = (
            raw_lifecycle if isinstance(raw_lifecycle, Mapping) else {}
        )
        status = str(lifecycle.get("status") or "active")
        raw_contract = domain.get("claim_contract")
        contract: Mapping[str, Any] = (
            raw_contract if isinstance(raw_contract, Mapping) else {}
        )
        action = str(contract.get("action_grammar") or "")
        inactive = status in {"blocked", "stale", "superseded", "retired"} or action == ACTION_IGNORE_OR_BLOCKED
        if inactive and not include_blocked:
            continue
        negative_text = " ".join(str(item) for item in domain.get("negative_cues") or [])
        negative_terms = _terms(negative_text)
        if prompt_terms & negative_terms or any(
            term and term in prompt_text.casefold() for term in negative_terms
        ):
            continue
        text = " ".join(
            [
                str(domain.get("domain_id") or ""),
                str(domain.get("title") or ""),
                " ".join(str(item) for item in domain.get("activation_cues") or []),
                " ".join(str(item) for item in domain.get("scope_labels") or []),
                " ".join(str(item) for item in domain.get("long_range_tendencies") or []),
            ]
        )
        domain_terms = _terms(text)
        overlap = _overlap_score(prompt_terms, prompt_text, domain_terms, text)
        if overlap <= 0:
            continue
        status_bonus = -3 if inactive else 0
        scored.append((overlap + status_bonus, str(domain.get("domain_id") or ""), dict(domain)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        continuity_domain_pointer(
            domain,
            why_it_may_matter_now="The current prompt overlaps this source-trailed continuity domain.",
            handle=(
                continuity_domain_handle(
                    domain,
                    clean_source_dir=clean_source_dir,
                    snapshot_path=snapshot_path,
                )
                if clean_source_dir is not None or snapshot_path is not None
                else None
            ),
        )
        for score, _, domain in scored
        if score > 0
    ][: max(0, limit)]


def domain_brief_for_deepen(
    *,
    domain_id: str,
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(snapshot, Mapping):
        return None
    for domain in snapshot.get("domains") or []:
        if not isinstance(domain, Mapping):
            continue
        if str(domain.get("domain_id") or "") != str(domain_id):
            continue
        refs = (
            domain.get("evidence_trail", {}).get("representative_refs")
            or domain.get("evidence_trail", {}).get("support_refs")
            or []
        )
        return {
            "kind": CONTINUITY_DOMAIN_DEEPEN_KIND,
            "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
            "domain_id": domain_id,
            "title": _safe_text(domain.get("title") or domain_id, 140),
            "working_conclusion_short": _safe_text(domain.get("working_conclusion_short"), 360),
            "scale": domain.get("scale") or "meso",
            "domain_type": domain.get("domain_type") or "recurring_question",
            "lifecycle": domain.get("lifecycle") or {},
            "evidence_trail": domain.get("evidence_trail") or {},
            "source_refs": safe_source_refs(refs)[:8],
            "claim_contract": domain.get("claim_contract") or {},
            "pinned_boundary_conditions": domain.get("pinned_boundary_conditions") or [],
            "lineage": domain.get("lineage") or {},
            "source_boundary": {
                **_domain_source_boundary(),
                "domain_brief_opened": True,
                "brief_is_still_not_clean_source": True,
            },
        }
    return None


def normalize_continuity_signal(row: Mapping[str, Any]) -> dict[str, Any] | None:
    producer = _safe_text(row.get("producer") or row.get("source") or row.get("surface"), 80)
    if producer not in SIGNAL_PRODUCERS:
        return None
    signal_kind = _safe_text(row.get("signal_kind") or row.get("kind") or producer, 100)
    source_refs = safe_source_refs(row.get("source_refs") or row.get("event_refs"))
    signal_id = _safe_text(row.get("signal_id"), 100) or _stable_id(
        producer,
        signal_kind,
        row.get("signal_labels") or row.get("labels"),
        source_refs,
        prefix="sig",
    )
    signal = {
        "signal_id": signal_id,
        "producer": producer,
        "signal_kind": signal_kind,
        "signal_detail": _safe_text(row.get("signal_detail") or row.get("detail") or "", 220),
        "signal_labels": _safe_list(row.get("signal_labels") or row.get("labels"), limit=12),
        "source_refs": source_refs[:8],
        "action_grammar": ACTION_DIRECTION_ONLY,
        "trust_level": TRUST_SEMANTIC_HINT,
        "memory_surface": "memory_atmosphere",
        "foreground_eligible": False,
        "truth_boundary": SIGNAL_PRODUCER_BOUNDARIES.get(producer, "signal_not_source_fact"),
        "cannot_claim": [
            "signal_is_fact",
            "signal_can_support_exact_claim",
            "signal_replaces_source_reopen",
        ],
    }
    return redact_sensitive_values(redact_private_paths(signal))


def _ordered_pathlet_fingerprint(pathlets: Sequence[Mapping[str, Any]]) -> str:
    ordered = []
    for pathlet in pathlets:
        ordered.append(
            [
                pathlet.get("pathlet_id"),
                [_ref_key(ref) for ref in pathlet.get("ordered_source_refs") or [] if isinstance(ref, Mapping)],
            ]
        )
    return _stable_id(ordered, prefix="pathorder")


def project_situation_glyph(
    *,
    signals: Sequence[Mapping[str, Any]],
    pathlets: Sequence[Mapping[str, Any]] | None = None,
    pinned_boundaries: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = [
        signal
        for row in signals
        if isinstance(row, Mapping)
        for signal in [normalize_continuity_signal(row)]
        if signal is not None
    ]
    pathlet_rows = [dict(row) for row in pathlets or [] if isinstance(row, Mapping)]
    boundary_rows = [dict(row) for row in pinned_boundaries or [] if isinstance(row, Mapping)]
    blocking = [
        row
        for row in boundary_rows
        if str(row.get("effect") or "") in HARD_BLOCKING_BOUNDARY_EFFECTS | {"redirect"}
    ]
    action = ACTION_IGNORE_OR_BLOCKED if blocking else ACTION_DIRECTION_ONLY
    status = "redirected_by_boundary" if blocking else "ok"
    labels = _safe_list(
        [
            label
            for signal in normalized
            for label in signal.get("signal_labels") or [signal.get("signal_kind")]
        ],
        limit=12,
    )
    path_order = _ordered_pathlet_fingerprint(pathlet_rows)
    glyph_id = _stable_id(
        [signal.get("signal_id") for signal in normalized],
        path_order,
        [
            (boundary.get("pin_id"), boundary.get("effect"))
            for boundary in boundary_rows
        ],
        prefix="glyph",
    )
    source_refs = _dedupe_refs(
        [ref for signal in normalized for ref in signal.get("source_refs") or []],
        limit=12,
    )
    glyph = {
        "kind": SITUATION_GLYPH_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "glyph_id": glyph_id,
        "status": status,
        "action_grammar": action,
        "trust_level": TRUST_IGNORE if blocking else TRUST_SEMANTIC_HINT,
        "memory_surface": "memory_atmosphere",
        "foreground_eligible": False,
        "atmosphere_labels": labels,
        "producer_counts": {
            producer: sum(1 for signal in normalized if signal.get("producer") == producer)
            for producer in sorted({str(signal.get("producer") or "") for signal in normalized})
        },
        "source_refs": source_refs,
        "pathlet_ids": [row.get("pathlet_id") for row in pathlet_rows if row.get("pathlet_id")],
        "boundary_redirects": [
            {
                "kind": row.get("kind") or row.get("boundary_kind"),
                "effect": row.get("effect"),
                "strength": row.get("strength"),
            }
            for row in blocking
        ],
        "truth_boundary": "situation_glyph_is_atmosphere_not_source_fact",
        "cannot_claim": [
            "glyph_is_fact",
            "glyph_is_user_profile",
            "glyph_predicts_future",
            "glyph_overrides_clean_source",
        ],
        "diagnostics": {
            "signal_count": len(normalized),
            "pathlet_count": len(pathlet_rows),
            "pathlet_order_fingerprint": path_order,
            "pathlet_order_sensitive": True,
            "pinned_boundary_count": len(boundary_rows),
        },
    }
    return redact_sensitive_values(redact_private_paths(glyph))
