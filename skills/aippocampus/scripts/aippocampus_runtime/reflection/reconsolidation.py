#!/usr/bin/env python3
"""Correction reconsolidation records and detached adjudication helpers.

This is the narrow runtime slice behind the Track D benchmark. It records
source-backed correction activation/outcome rows and can produce conservative
adjudication candidates for later review. It deliberately does not install
foreground hooks or promote anything into formal memory.

Host-event capture is intentionally an opt-in adapter: it can turn
UserPromptSubmit / Stop-like payloads into sanitized append-only rows only when
the payload carries source refs. Default hooks should call it only after an
operator chooses a write path, because correction rows are private staging
evidence rather than ambient recall output.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    safe_path_name,
    sanitize_external_model_text,
    stable_text_fingerprint,
)
from aippocampus_runtime.question.source_refs import compact_source_refs, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.texture_consumption import (
    select_texture_signals,
    texture_signal_source_refs,
    texture_signal_summary,
)

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-correction-reconsolidation-v1"

ACTIVATION_KIND = "correction_activation_event"
OUTCOME_KIND = "correction_outcome_event"
ADJUDICATION_KIND = "correction_adjudication_candidate"
ACTIVE_ANCHOR_KIND = "correction_active_task_anchor"

EVENT_KINDS = {ACTIVATION_KIND, OUTCOME_KIND, ADJUDICATION_KIND}

HOOK_STAGES = (
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "PreCompact",
    "PostCompact",
)
TARGET_TYPES = (
    "claim",
    "scope",
    "route",
    "default",
    "test",
    "doc_contract",
    "tool_result",
    "handoff",
)
PROVISIONAL_IMPORTANCE = ("local", "active_task", "project", "unknown")
OUTCOME_SIGNALS = ("adopted", "ignored", "contradicted", "unclear")
COMPACTION_STATES = ("visible", "post_compaction", "horizon_lost")
ADJUDICATION_STATUSES = (
    "valid_adopted",
    "valid_ignored",
    "refuted",
    "superseded",
    "local_only",
    "uncertain",
)
ACTIVE_ANCHOR_STATUSES = {"valid_adopted", "valid_ignored"}
SUPPRESS_ANCHOR_STATUSES = {"refuted", "superseded", "local_only", "uncertain"}

LOCAL_PATH_RE = re.compile(
    r"(?i)(^[a-z]:[\\/])|(^/(Users|home|root|tmp|var|mnt|Volumes|private)/)|(^~[\\/])"
)


def stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return stable_text_fingerprint(raw, namespace="correction-reconsolidation-id", prefix=prefix, length=length)


def _sanitize_text(
    value: Any,
    *,
    max_chars: int,
    policies: list[dict[str, Any]],
) -> str:
    sanitized, policy = sanitize_external_model_text(str(value or ""))
    policies.append(policy)
    return compact_text(sanitized, max_chars)


def _privacy_scan(policies: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    redaction_types: list[str] = []
    redaction_count = 0
    hard_block = False
    for policy in policies:
        redaction_count += int(policy.get("redaction_count") or 0)
        hard_block = hard_block or bool(policy.get("hard_block"))
        redaction_types.extend(str(item) for item in policy.get("redaction_types") or [])
    return {
        "raw_text_stored": False,
        "raw_tool_payloads_stored": False,
        "local_paths_stored": False,
        "secrets_stored": False,
        "redacted": bool(redaction_count or hard_block),
        "redaction_count": redaction_count,
        "redaction_types": unique_preserve(redaction_types, limit=8),
        "hard_block": hard_block,
    }


def _workspace_fields(workspace: str | None, policies: list[dict[str, Any]]) -> dict[str, Any]:
    raw = str(workspace or "").strip()
    if not raw:
        return {"workspace": ""}
    sanitized = _sanitize_text(raw, max_chars=160, policies=policies)
    path_like = bool(LOCAL_PATH_RE.search(raw) or "\\" in raw or "/" in raw)
    if not path_like:
        return {"workspace": sanitized}
    normalized = raw.replace("\\", "/").rstrip("/")
    label = safe_path_name(normalized.rsplit("/", 1)[-1] or "workspace", "workspace")
    return {
        "workspace": label,
        "workspace_sha1": stable_text_fingerprint(
            normalized.casefold(),
            namespace="correction-workspace",
            length=16,
        ),
        "workspace_privacy": "local_path_redacted_to_label_and_hash",
    }


def _safe_relative_path(value: str) -> str | None:
    text = value.replace("\\", "/").strip()
    if not text or LOCAL_PATH_RE.search(text) or text.startswith("/"):
        return None
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def sanitize_file_hints(
    values: Sequence[Any] | None,
    *,
    workspace: str | None = None,
    policies: list[dict[str, Any]] | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    policies = policies if policies is not None else []
    workspace_norm = str(workspace or "").replace("\\", "/").rstrip("/").casefold()
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for value in values or []:
        raw = str(value or "").strip()
        if not raw:
            continue
        normalized = raw.replace("\\", "/").rstrip("/")
        normalized_folded = normalized.casefold()
        relative = _safe_relative_path(normalized)
        if workspace_norm and normalized_folded.startswith(workspace_norm + "/"):
            relative = _safe_relative_path(normalized[len(workspace_norm) + 1 :])
        if relative:
            safe = _sanitize_text(relative, max_chars=220, policies=policies)
            row = {"path_kind": "repo_relative", "path": safe}
        else:
            _sanitize_text(raw, max_chars=220, policies=policies)
            row = {
                "path_kind": "redacted_local_path",
                "path_sha1": stable_text_fingerprint(
                    raw,
                    namespace="correction-path",
                    length=16,
                ),
            }
        key = (str(row.get("path_kind") or ""), str(row.get("path") or row.get("path_sha1") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def sanitize_source_refs(
    values: Any,
    *,
    policies: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    refs = compact_source_refs(values, limit=limit)
    out: list[dict[str, Any]] = []
    for ref in refs:
        clean: dict[str, Any] = {}
        for key, value in ref.items():
            if isinstance(value, str):
                clean[key] = _sanitize_text(value, max_chars=220, policies=policies)
            else:
                clean[key] = value
        out.append(clean)
    return out


def merge_source_refs(*groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for group in groups:
        for ref in group:
            if not isinstance(ref, Mapping):
                continue
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
    return refs[:12]


def sanitize_evidence_items(
    values: Sequence[Any] | None,
    *,
    policies: list[dict[str, Any]],
    default_kind: str,
    limit: int = 16,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in values or []:
        if isinstance(value, Mapping):
            kind = _sanitize_text(value.get("kind") or default_kind, max_chars=48, policies=policies)
            status = _sanitize_text(value.get("status") or "", max_chars=48, policies=policies)
            summary = _sanitize_text(
                value.get("summary") or value.get("message") or "",
                max_chars=360,
                policies=policies,
            )
            refs = sanitize_source_refs(value.get("source_refs") or [], policies=policies, limit=4)
        else:
            kind = default_kind
            status = ""
            summary = _sanitize_text(value, max_chars=360, policies=policies)
            refs = []
        if not summary and not refs:
            continue
        row: dict[str, Any] = {
            "kind": kind or default_kind,
            "summary": summary,
        }
        if status:
            row["status"] = status
        if refs:
            row["source_refs"] = refs
        out.append(row)
        if len(out) >= limit:
            break
    return out


def build_activation_event(
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    correction_surface: str,
    source_refs: Sequence[Mapping[str, Any]],
    target_type: str,
    provisional_importance: str = "unknown",
    corrected_claim_source_refs: Sequence[Mapping[str, Any]] | None = None,
    hook_stage: str = "UserPromptSubmit",
    created_at: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    target_type = target_type if target_type in TARGET_TYPES else ""
    if not target_type:
        raise ValueError(f"target_type must be one of {', '.join(TARGET_TYPES)}")
    provisional_importance = (
        provisional_importance if provisional_importance in PROVISIONAL_IMPORTANCE else "unknown"
    )
    if hook_stage not in HOOK_STAGES:
        raise ValueError(f"hook_stage must be one of {', '.join(HOOK_STAGES)}")
    policies: list[dict[str, Any]] = []
    refs = sanitize_source_refs(source_refs, policies=policies)
    if not refs:
        raise ValueError("correction_activation_event requires source_refs")
    corrected_refs = sanitize_source_refs(corrected_claim_source_refs or [], policies=policies)
    surface = _sanitize_text(correction_surface, max_chars=420, policies=policies)
    if not surface:
        surface = "<redacted:correction-surface>"
    thread = _sanitize_text(thread_id, max_chars=140, policies=policies)
    epoch = _sanitize_text(topic_epoch, max_chars=100, policies=policies)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVATION_KIND,
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "event_id": event_id
        or stable_id("corr_act", thread, epoch, target_type, surface, refs, length=20),
        "thread_id": thread,
        **_workspace_fields(workspace, policies),
        "topic_epoch": epoch,
        "hook_stage": hook_stage,
        "source_refs": refs,
        "corrected_claim_source_refs": corrected_refs,
        "correction_surface": surface,
        "target_type": target_type,
        "provisional_importance": provisional_importance,
        "status": "staging",
        "source": "deterministic_correction_reconsolidation",
        "formal_memory_promoted": False,
        "review_required": True,
    }
    payload["privacy_scan"] = _privacy_scan(policies)
    return payload


def build_outcome_event(
    *,
    activation_event_id: str,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    outcome_summary: str,
    source_refs: Sequence[Mapping[str, Any]],
    adoption_signal: str = "unclear",
    final_claim_source_refs: Sequence[Mapping[str, Any]] | None = None,
    changed_files: Sequence[Any] | None = None,
    verification_evidence: Sequence[Any] | None = None,
    tool_evidence: Sequence[Any] | None = None,
    texture_evidence: Sequence[Mapping[str, Any]] | None = None,
    follow_up_source_refs: Sequence[Mapping[str, Any]] | None = None,
    adjudication_hint: str | None = None,
    superseded_by_activation_event_id: str | None = None,
    created_at: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if adoption_signal not in OUTCOME_SIGNALS:
        raise ValueError(f"adoption_signal must be one of {', '.join(OUTCOME_SIGNALS)}")
    if adjudication_hint and adjudication_hint not in ADJUDICATION_STATUSES:
        raise ValueError(f"adjudication_hint must be one of {', '.join(ADJUDICATION_STATUSES)}")
    policies: list[dict[str, Any]] = []
    refs = sanitize_source_refs(source_refs, policies=policies)
    if not refs:
        raise ValueError("correction_outcome_event requires source_refs")
    final_refs = sanitize_source_refs(final_claim_source_refs or [], policies=policies)
    follow_up_refs = sanitize_source_refs(follow_up_source_refs or [], policies=policies)
    summary = _sanitize_text(outcome_summary, max_chars=520, policies=policies)
    texture_selection = select_texture_signals(texture_evidence or [], consumer="correction", limit=12)
    texture_signals = [
        dict(signal)
        for signal in texture_selection.get("signals") or []
        if isinstance(signal, Mapping)
    ]
    texture_summary = texture_signal_summary(
        texture_signals,
        consumer="correction",
        suppression_reasons=(texture_selection.get("diagnostics") or {}).get("suppression_reasons") or {},
    )
    thread = _sanitize_text(thread_id, max_chars=140, policies=policies)
    epoch = _sanitize_text(topic_epoch, max_chars=100, policies=policies)
    activation_id = _sanitize_text(activation_event_id, max_chars=120, policies=policies)
    supersedes = _sanitize_text(
        superseded_by_activation_event_id or "",
        max_chars=120,
        policies=policies,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTCOME_KIND,
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "event_id": event_id
        or stable_id("corr_out", activation_id, thread, epoch, summary, refs, length=20),
        "activation_event_id": activation_id,
        "thread_id": thread,
        **_workspace_fields(workspace, policies),
        "topic_epoch": epoch,
        "source_refs": refs,
        "final_claim_source_refs": final_refs,
        "outcome_summary": summary or "<redacted:outcome-summary>",
        "adoption_signal": adoption_signal,
        "changed_files": sanitize_file_hints(changed_files, workspace=workspace, policies=policies),
        "verification_evidence": sanitize_evidence_items(
            verification_evidence,
            policies=policies,
            default_kind="verification",
        ),
        "tool_evidence": sanitize_evidence_items(
            tool_evidence,
            policies=policies,
            default_kind="tool_result",
        ),
        "texture_evidence": texture_signals,
        "source_texture_consumption": texture_summary,
        "follow_up_source_refs": follow_up_refs,
        "status": "staging",
        "source": "deterministic_correction_reconsolidation",
        "formal_memory_promoted": False,
        "review_required": True,
    }
    if adjudication_hint:
        payload["adjudication_hint"] = adjudication_hint
    if supersedes:
        payload["superseded_by_activation_event_id"] = supersedes
    payload["privacy_scan"] = _privacy_scan(policies)
    return payload


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


def append_events(path: Path, events: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for event in events:
            if event.get("kind") not in EVENT_KINDS:
                raise ValueError(f"unsupported correction reconsolidation event kind: {event.get('kind')}")
            fh.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
            count += 1
    return count


def _status_for_pair(activation: Mapping[str, Any], outcome: Mapping[str, Any] | None) -> str:
    if outcome:
        hint = str(outcome.get("adjudication_hint") or "")
        if hint in ADJUDICATION_STATUSES:
            return hint
        if outcome.get("superseded_by_activation_event_id"):
            return "superseded"
        signal = str(outcome.get("adoption_signal") or "unclear")
        if signal == "adopted":
            if str(activation.get("provisional_importance") or "") == "local":
                return "local_only"
            return "valid_adopted"
        if signal == "ignored":
            return "valid_ignored"
        if signal == "contradicted":
            return "refuted"
    return "uncertain"


def route_for_adjudication(status: str) -> str:
    if status in ACTIVE_ANCHOR_STATUSES:
        return "active_task_anchor"
    if status == "refuted":
        return "refuted_correction"
    if status == "superseded":
        return "suppress_stale_anchor"
    if status == "local_only":
        return "local_only_expiry"
    return "confirm_when_relevant"


def _recommendation_for(status: str) -> str:
    if status == "valid_adopted":
        return "Use as an active task anchor after compaction or horizon loss; review before durable memory."
    if status == "valid_ignored":
        return "Surface as a relevant foreground warning if the next action risks repeating the ignored correction."
    if status == "refuted":
        return "Do not resurface as guidance; keep only as a refuted correction note."
    if status == "superseded":
        return "Suppress this stale anchor and prefer the successor correction when available."
    if status == "local_only":
        return "Keep within the current task or handoff only; expire outside that scope."
    return "Ask for confirmation only when a current action depends on this correction."


def build_adjudication_candidate(
    activation: Mapping[str, Any],
    outcome: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = _status_for_pair(activation, outcome)
    outcome_refs = outcome.get("source_refs") or [] if outcome else []
    source_refs = merge_source_refs(
        activation.get("source_refs") or [],
        activation.get("corrected_claim_source_refs") or [],
        outcome_refs,
        outcome.get("final_claim_source_refs") or [] if outcome else [],
        outcome.get("follow_up_source_refs") or [] if outcome else [],
        texture_signal_source_refs(outcome.get("texture_evidence") or []) if outcome else [],
    )
    activation_id = str(activation.get("event_id") or "")
    outcome_id = str(outcome.get("event_id") or "") if outcome else ""
    route = route_for_adjudication(status)
    correction_surface = compact_text(str(activation.get("correction_surface") or ""), 300)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ADJUDICATION_KIND,
        "created_at": now_utc(),
        "prompt_version": PROMPT_VERSION,
        "candidate_id": stable_id("corr_adj", activation_id, outcome_id, status, length=20),
        "activation_event_id": activation_id,
        "outcome_event_id": outcome_id or None,
        "thread_id": activation.get("thread_id"),
        "workspace": activation.get("workspace"),
        "workspace_sha1": activation.get("workspace_sha1"),
        "topic_epoch": activation.get("topic_epoch"),
        "target_type": activation.get("target_type"),
        "correction_surface": correction_surface,
        "adjudication_status": status,
        "route": route,
        "status": "staging",
        "review_state": "staging",
        "truth_status": "candidate_hypothesis_until_reviewed",
        "formal_memory_promoted": False,
        "candidate_type": "correction_reconsolidation",
        "title": compact_text(f"Correction reconsolidation: {status}", 160),
        "summary": compact_text(
            f"{status} correction candidate for {activation.get('target_type')}: {correction_surface}",
            620,
        ),
        "recommendation": _recommendation_for(status),
        "source_event_ids": [value for value in [activation_id, outcome_id] if value],
        "source_refs": source_refs,
        "evidence": {
            "activation_event_id": activation_id,
            "outcome_event_id": outcome_id or None,
            "outcome_signal": outcome.get("adoption_signal") if outcome else None,
            "changed_file_count": len(outcome.get("changed_files") or []) if outcome else 0,
            "verification_evidence_count": len(outcome.get("verification_evidence") or [])
            if outcome
            else 0,
            "tool_evidence_count": len(outcome.get("tool_evidence") or []) if outcome else 0,
            "texture_evidence_count": len(outcome.get("texture_evidence") or []) if outcome else 0,
            "texture_signal_kinds": unique_preserve(
                [
                    str(item.get("signal_kind") or "")
                    for item in outcome.get("texture_evidence") or []
                    if isinstance(item, Mapping)
                ],
                limit=8,
            )
            if outcome
            else [],
        },
        "artifact_boundary": {
            "detached_adjudication": True,
            "model_output": "none_deterministic_prototype",
            "truth_status": "candidate_hypothesis_until_reviewed",
            "review_or_validation_required": True,
            "formal_memory": False,
        },
    }


def adjudicate_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    activations = [
        event for event in events if event.get("kind") == ACTIVATION_KIND and event.get("event_id")
    ]
    outcomes_by_activation: dict[str, list[Mapping[str, Any]]] = {}
    for event in events:
        if event.get("kind") != OUTCOME_KIND:
            continue
        activation_id = str(event.get("activation_event_id") or "")
        if activation_id:
            outcomes_by_activation.setdefault(activation_id, []).append(event)

    candidates: list[dict[str, Any]] = []
    for activation in sorted(activations, key=lambda item: str(item.get("created_at") or "")):
        activation_id = str(activation.get("event_id") or "")
        outcomes = sorted(
            outcomes_by_activation.get(activation_id, []),
            key=lambda item: str(item.get("created_at") or ""),
        )
        if not outcomes:
            candidates.append(build_adjudication_candidate(activation, None))
            continue
        candidates.append(build_adjudication_candidate(activation, outcomes[-1]))
    return candidates


def should_surface_candidate(
    candidate: Mapping[str, Any],
    *,
    context_state: str,
    action_relevant: bool = True,
    visible_context_has_source: bool = False,
    already_injected_event_ids: set[str] | None = None,
) -> bool:
    if not action_relevant:
        return False
    if context_state not in {"post_compaction", "horizon_lost"}:
        return False
    if visible_context_has_source:
        return False
    if str(candidate.get("kind") or "") != ADJUDICATION_KIND:
        return False
    if str(candidate.get("adjudication_status") or "") not in ACTIVE_ANCHOR_STATUSES:
        return False
    if str(candidate.get("route") or "") != "active_task_anchor":
        return False
    activation_id = str(candidate.get("activation_event_id") or "")
    if already_injected_event_ids and activation_id in already_injected_event_ids:
        return False
    return True


def render_active_task_anchors(
    candidates: Sequence[Mapping[str, Any]],
    *,
    context_state: str,
    action_relevant: bool = True,
    visible_context_has_source: bool = False,
    already_injected_event_ids: set[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for candidate in candidates:
        if not should_surface_candidate(
            candidate,
            context_state=context_state,
            action_relevant=action_relevant,
            visible_context_has_source=visible_context_has_source,
            already_injected_event_ids=already_injected_event_ids,
        ):
            continue
        status = str(candidate.get("adjudication_status") or "")
        instruction = (
            "Keep this source-backed correction in view; it was ignored before."
            if status == "valid_ignored"
            else "Continue following this source-backed correction."
        )
        anchors.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ACTIVE_ANCHOR_KIND,
                "candidate_id": candidate.get("candidate_id"),
                "activation_event_id": candidate.get("activation_event_id"),
                "outcome_event_id": candidate.get("outcome_event_id"),
                "adjudication_status": status,
                "route": candidate.get("route"),
                "context_state": context_state,
                "title": candidate.get("title"),
                "summary": candidate.get("summary"),
                "instruction": instruction,
                "source_refs": candidate.get("source_refs") or [],
                "truth_status": candidate.get("truth_status"),
                "formal_memory_promoted": False,
            }
        )
        if len(anchors) >= limit:
            break
    return anchors


def run_adjudication(
    *,
    events_path: Path,
    output_path: Path | None = None,
    no_write: bool = False,
    context_state: str | None = None,
) -> dict[str, Any]:
    events = iter_jsonl(events_path)
    candidates = adjudicate_events(events)
    wrote_count = 0
    if output_path and not no_write and candidates:
        wrote_count = append_events(output_path, candidates)
    anchors: list[dict[str, Any]] = []
    if context_state:
        anchors = render_active_task_anchors(candidates, context_state=context_state)
    return {
        "ok": True,
        "kind": "aippocampus_correction_reconsolidation_run",
        "schema_version": SCHEMA_VERSION,
        "events_input": str(events_path),
        "output": str(output_path) if output_path else None,
        "activation_event_count": sum(1 for event in events if event.get("kind") == ACTIVATION_KIND),
        "outcome_event_count": sum(1 for event in events if event.get("kind") == OUTCOME_KIND),
        "candidate_count": len(candidates),
        "wrote_count": wrote_count,
        "no_write": no_write,
        "candidates": candidates,
        "anchors": anchors,
        "cannot_claim": [
            "live_hook_capture",
            "live_semantic_adjudication_quality",
            "formal_memory_promotion",
            "private_real_history_compaction_survival",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--context-state", choices=COMPACTION_STATES)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    events_path = Path(args.events_input).resolve()
    output_path = Path(args.output).resolve() if args.output else None
    try:
        result = run_adjudication(
            events_path=events_path,
            output_path=output_path,
            no_write=args.no_write,
            context_state=args.context_state,
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
        print(f"activation events: {result['activation_event_count']}")
        print(f"outcome events: {result['outcome_event_count']}")
        print(f"adjudication candidates: {result['candidate_count']}")
        if output_path:
            print(f"output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
