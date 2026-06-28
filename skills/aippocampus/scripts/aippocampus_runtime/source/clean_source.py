#!/usr/bin/env python3
"""Build an AIppocampus clean-source corpus from a host transcript source.

Clean source is original visible conversation text, not a summary. It removes
raw host envelopes, tool payloads, injected workspace instructions, and routine
commentary when a turn has a final answer. Raw host transcripts remain the audit
source, but day-to-day recall can use this smaller source-backed corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    codex_home,
    default_thread_clean_source_dir,
    file_sha256,
    locate_rollout,
    now_utc,
    resolve_artifact_path,
    stable_text_join_id,
)
from aippocampus_runtime.io_integrity import atomic_write_json, atomic_write_jsonl
from aippocampus_runtime.recall.route_notes import extract_route_note_candidates_for_source
from aippocampus_runtime.source.behavior_events import extract_rollout_behavior_events
from aippocampus_runtime.source.host_internal_filter import filter_host_internal_clean_text
from aippocampus_runtime.source.material_sanitizer import (
    classify_source_material,
    clean_source_material_contract,
)
from aippocampus_runtime.source.normalization_loss import (
    empty_provider_normalization_loss,
    finalize_provider_normalization_loss,
)
from aippocampus_runtime.source.redaction_profiles import write_clean_source_redaction_profiles
from aippocampus_runtime.source.scope_labels import (
    SCOPE_LABEL_ORDER,
    infer_scope_labels,
)
from aippocampus_runtime.source.scope_labels import (
    merge_scope_labels as _merge_scope_labels,
)
from aippocampus_runtime.source.source_texture import materialize_source_texture_sidecar
from conversation_sources import ConversationProvider, create_conversation_provider
from conversation_sources.normalized import stable_source_ref

LEGACY_OUTPUT_DIR = ".aippocampus/clean-source"
CLEAN_SOURCE_SCHEMA_VERSION = 2
SIGNATURE_CONTRACT_VERSION = "aippocampus-signature-sidecar-v1"
SCOPE_LABEL_POLICY_VERSION = "aippocampus-scope-labels-v1"
LOSS_ACCOUNTING_REASON_KEYS = (
    "no_final_answer",
    "assistant_missing",
    "tool_only_turn",
    "empty_after_filter",
    "host_internal_empty_after_filter",
    "user_empty_after_filter",
    "assistant_empty_after_filter",
    "fallback_empty",
    "assistant_commentary_shadowed_by_final",
    "tool_payload_not_clean_source",
    "unselected_assistant_message",
    "user_missing",
)


def _provider_normalization_loss(provider: ConversationProvider) -> dict[str, Any]:
    loss = getattr(provider, "last_normalization_loss", None)
    if isinstance(loss, dict):
        return dict(loss)
    report = finalize_provider_normalization_loss(empty_provider_normalization_loss(provider.name))
    report["status"] = "unreported_by_provider"
    report["source_boundary"] = (
        "This provider did not expose parser/policy loss diagnostics; absence of counts "
        "is not proof that every raw transcript row was normalized."
    )
    report.setdefault("warning_codes", []).append("provider_normalization_loss_unreported")
    return report


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _semantic_key(role: str, phase: str, text: str) -> str:
    normalized = " ".join(text.casefold().split())
    # Clean-source ids are persisted join keys across messages, turns, sidecars,
    return stable_text_join_id("sem", role, phase, normalized, sep="\0", length=20)


def _clean_behavior_events(
    events: list[dict[str, Any]],
    *,
    source_id: str,
    source_provider: str,
    session_id: str | None,
) -> list[dict[str, Any]]:
    clean_events: list[dict[str, Any]] = []
    for event in events:
        line_no = event.get("line")
        event_kind = str(event.get("event_kind") or "")
        hard_event_kind = str(event.get("hard_event_kind") or event_kind)
        event_id = stable_text_join_id(
            "evt",
            source_id,
            line_no,
            event_kind,
            event.get("call_ref"),
            event.get("observation_sha256") or event.get("input_sha256"),
            sep="\0",
            length=20,
        )
        status = str(event.get("status") or "observed")
        command_class = str(event.get("command_class") or "tool")
        command_family = str(event.get("command_family") or command_class)
        tool_name = str(event.get("tool_name") or "tool")
        text = (
            f"{tool_name} {status}; command_class={command_class}; "
            f"command_family={command_family}; event={hard_event_kind}"
        )
        if event.get("exit_code") is not None:
            text += f"; exit_code={event.get('exit_code')}"
        if event.get("failure_family"):
            text += f"; failure_family={event.get('failure_family')}"
        row = {
            "id": event_id,
            "event_id": event_id,
            "source_id": source_id,
            "source_ref": stable_source_ref(source_provider, session_id, int(line_no))
            if isinstance(line_no, int)
            else None,
            "source_line": line_no,
            "raw_start_line": line_no,
            "raw_end_line": line_no,
            "timestamp": event.get("timestamp"),
            "turn_index": event.get("turn_index"),
            "event_kind": event_kind,
            "hard_event_kind": hard_event_kind,
            "tool_payload_kind": event.get("tool_payload_kind"),
            "tool_name": tool_name,
            "call_ref": event.get("call_ref"),
            "command_class": command_class,
            "tool_intent": event.get("tool_intent"),
            "command_family": command_family,
            "target_class": event.get("target_class"),
            "test_target_class": event.get("test_target_class"),
            "failure_family": event.get("failure_family"),
            "critical_operation_family": event.get("critical_operation_family"),
            "exit_code": event.get("exit_code"),
            "status": status,
            "behavior_backed": bool(event.get("behavior_backed")),
            "input_sha256": event.get("input_sha256"),
            "observation_sha256": event.get("observation_sha256"),
            "input_field_names": event.get("input_field_names") or [],
            "path_count": event.get("path_count"),
            "path_categories": event.get("path_categories") or [],
            "path_extensions": event.get("path_extensions") or [],
            "path_fingerprints": event.get("path_fingerprints") or [],
            "repo_relative_breadcrumbs": event.get("repo_relative_breadcrumbs") or [],
            "generated_file": event.get("generated_file"),
            "generated_file_reason": event.get("generated_file_reason"),
            "text": text,
        }
        clean_events.append(
            {key: value for key, value in row.items() if value not in (None, "", [])}
        )
    return clean_events


def _empty_loss_accounting(messages: list[dict], turns: list[dict]) -> dict[str, Any]:
    return {
        "scope": "post_provider_normalization",
        "source_boundary": (
            "Counts describe clean-source filtering after the provider has already parsed "
            "the transcript. Raw JSONL/parser losses need provider diagnostics."
        ),
        "normalized_message_count": len(messages),
        "normalized_turn_count": len(turns),
        "clean_message_count": 0,
        "clean_turn_count": 0,
        "filtered_or_dropped_message_count": 0,
        "user_only_turn_count": 0,
        "empty_clean_turn_count": 0,
        "turns_with_no_clean_assistant_count": 0,
        "reason_counts": {key: 0 for key in LOSS_ACCOUNTING_REASON_KEYS},
        "warning_codes": [],
    }


def _count_loss(loss: dict[str, Any], reason: str, amount: int = 1) -> None:
    reason_counts = loss.setdefault("reason_counts", {})
    reason_counts[reason] = int(reason_counts.get(reason) or 0) + amount


def _finalize_loss_accounting(
    loss: dict[str, Any],
    clean_messages: list[dict],
    clean_turns: list[dict],
) -> dict[str, Any]:
    loss["clean_message_count"] = len(clean_messages)
    loss["clean_turn_count"] = len(clean_turns)
    loss["filtered_or_dropped_message_count"] = max(
        0,
        int(loss.get("normalized_message_count") or 0) - len(clean_messages),
    )
    for turn in clean_turns:
        has_user = bool(turn.get("user_message_id"))
        has_assistant = bool(turn.get("assistant_message_id"))
        if has_user and not has_assistant:
            loss["user_only_turn_count"] += 1
        if not has_assistant:
            loss["turns_with_no_clean_assistant_count"] += 1
        if not turn.get("message_ids"):
            loss["empty_clean_turn_count"] += 1

    turn_count = max(1, len(clean_turns))
    user_only_ratio = float(loss["user_only_turn_count"]) / float(turn_count)
    if loss["user_only_turn_count"] >= 3 and user_only_ratio >= 0.25:
        loss["warning_codes"].append("user_only_turn_spike")
    if loss["empty_clean_turn_count"]:
        loss["warning_codes"].append("empty_clean_turns")
    return loss


def _clean_messages(
    messages: list[dict], turns: list[dict], source_id: str, *, source_provider: str
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    by_turn: dict[int, list[dict]] = {}
    for message in messages:
        turn_index = message.get("turn_index")
        if isinstance(turn_index, int):
            by_turn.setdefault(turn_index, []).append(message)

    clean_messages: list[dict] = []
    clean_turns: list[dict] = []
    loss_accounting = _empty_loss_accounting(messages, turns)

    for turn in turns:
        turn_id = int(turn["id"])
        items = by_turn.get(turn_id, [])
        user = next((item for item in items if item.get("role") == "user"), None)
        final = next((item for item in items if item.get("is_final")), None)
        assistant = final
        assistant_phase = "final_answer"
        if turn.get("final_line") is None:
            _count_loss(loss_accounting, "no_final_answer")
        if assistant is None:
            fallback_line = turn.get("fallback_assistant_line")
            assistant = next((item for item in items if item.get("line") == fallback_line), None)
            assistant_phase = "commentary_fallback" if assistant else ""
        if user is None:
            _count_loss(loss_accounting, "user_missing")
        if assistant is None:
            _count_loss(loss_accounting, "assistant_missing")
            if (int(turn.get("tool_call_count") or 0) + int(turn.get("tool_output_count") or 0)) > 0:
                _count_loss(loss_accounting, "tool_only_turn")

        turn_uid = stable_text_join_id(
            "turn",
            source_id,
            turn_id,
            turn.get("user_line"),
            turn.get("start_line"),
            sep="\0",
            length=20,
        )
        kept: list[dict] = []
        selected_ids = {id(item) for item in (user, assistant) if item}
        for item in (user, assistant):
            if not item:
                continue
            phase = item.get("phase") or ""
            text, host_internal_filtered = filter_host_internal_clean_text(item.get("text") or "")
            if not text.strip():
                _count_loss(loss_accounting, "empty_after_filter")
                if host_internal_filtered:
                    _count_loss(loss_accounting, "host_internal_empty_after_filter")
                if item.get("role") == "user":
                    _count_loss(loss_accounting, "user_empty_after_filter")
                elif assistant_phase == "commentary_fallback":
                    _count_loss(loss_accounting, "fallback_empty")
                else:
                    _count_loss(loss_accounting, "assistant_empty_after_filter")
                continue
            material = classify_source_material(
                text,
                source_surface=source_provider,
                metadata={"provider": source_provider, "phase": phase},
            )
            content_sha256 = _content_sha256(text)
            message_id = stable_text_join_id(
                "msg",
                source_id,
                item.get("line"),
                item.get("role"),
                phase,
                content_sha256,
                sep="\0",
                length=20,
            )
            kept_item = {
                "id": message_id,
                "message_id": message_id,
                "turn_id": turn_uid,
                "source_id": source_id,
                "source_ref": item.get("source_ref"),
                "source_line": item.get("line"),
                "raw_start_line": item.get("raw_start_line") or item.get("line"),
                "raw_end_line": item.get("raw_end_line") or item.get("line"),
                "timestamp": item.get("timestamp"),
                "role": item.get("role"),
                "kind": item.get("kind"),
                "phase": phase,
                "turn_index": turn_id,
                "is_final": bool(item.get("is_final")),
                "text_sha1": item.get("sha1"),
                "content_sha256": content_sha256,
                "semantic_key": _semantic_key(str(item.get("role") or ""), phase, text),
                "signature_key": message_id,
                "scope_labels": infer_scope_labels(text),
                "material_class": material["material_class"],
                "public_projection_policy": material["public_projection_policy"],
                "source_claim_policy": material["source_claim_policy"],
                "text": text,
            }
            if host_internal_filtered:
                kept_item["host_internal_filtered"] = True
            kept.append(kept_item)
            clean_messages.append(kept_item)

        for item in items:
            if id(item) in selected_ids:
                continue
            role = str(item.get("role") or "")
            if role in {"tool", "event"}:
                _count_loss(loss_accounting, "tool_payload_not_clean_source")
            elif role == "assistant" and final is not None and item.get("phase") == "commentary":
                _count_loss(loss_accounting, "assistant_commentary_shadowed_by_final")
            elif role == "assistant":
                _count_loss(loss_accounting, "unselected_assistant_message")

        user_message = next((item for item in kept if item.get("role") == "user"), None)
        assistant_message = next((item for item in kept if item.get("role") == "assistant"), None)
        clean_ordinals = [len(clean_messages) - len(kept) + idx for idx in range(len(kept))]
        clean_turns.append(
            {
                "turn_id": turn_uid,
                "source_id": source_id,
                "turn_index": turn_id,
                "user_line": user.get("line") if user else None,
                "assistant_line": assistant.get("line") if assistant else None,
                "user_message_id": user_message.get("message_id") if user_message else None,
                "assistant_message_id": assistant_message.get("message_id")
                if assistant_message
                else None,
                "message_ids": [item["message_id"] for item in kept],
                "assistant_phase": assistant_phase,
                "start_line": turn.get("start_line"),
                "end_line": turn.get("end_line"),
                "raw_start_line": turn.get("start_line"),
                "raw_end_line": turn.get("end_line"),
                "clean_start_ordinal": clean_ordinals[0] if clean_ordinals else None,
                "clean_end_ordinal": clean_ordinals[-1] if clean_ordinals else None,
                "message_count": len(kept),
                "scope_labels": _merge_scope_labels(kept),
            }
        )

    return clean_messages, clean_turns, _finalize_loss_accounting(
        loss_accounting,
        clean_messages,
        clean_turns,
    )


def build_clean_source(
    cwd: str | Path,
    *,
    rollout: str | Path | None = None,
    output_dir: str | Path | None = None,
    hash_source: bool = False,
    provider_name: str = "codex",
    provider: ConversationProvider | None = None,
    redaction_profiles: list[str] | None = None,
) -> dict[str, Any]:
    """Build normalized clean source from a host transcript.

    aippocampus-stage-map: locate provider/source -> normalize host turns ->
    materialize clean messages/events -> emit canonical manifests/profiles.
    Keep persisted id-shape changes outside this orchestrator unless paired
    with an explicit source-id alias migration.
    """

    cwd = Path(cwd).resolve()
    active_provider = provider or create_conversation_provider(
        provider_name,
        codex_home_dir=codex_home(),
    )
    source_path = Path(rollout) if rollout else None
    if source_path is None:
        if active_provider.name == "codex":
            source_path = locate_rollout(cwd, codex_home())
        else:
            source_path = active_provider.locate_current(cwd).path
    if not source_path.is_absolute():
        source_path = cwd / source_path

    out = resolve_artifact_path(output_dir, cwd, default_thread_clean_source_dir(cwd, source_path))
    out.mkdir(parents=True, exist_ok=True)

    meta = active_provider.read_metadata(source_path) or {}
    messages, turns = active_provider.read_normalized_messages(source_path, include_tools=False)
    provider_normalization_loss = _provider_normalization_loss(active_provider)

    source_thread_key = active_provider.thread_key(source_path, meta)
    source_key = source_thread_key or meta.get("id") or str(source_path.resolve())
    source_id = stable_text_join_id("src", source_key, sep="\0", length=20)
    clean_messages, clean_turns, loss_accounting = _clean_messages(
        messages,
        turns,
        source_id,
        source_provider=active_provider.name,
    )
    clean_events = (
        _clean_behavior_events(
            extract_rollout_behavior_events(source_path),
            source_id=source_id,
            source_provider=active_provider.name,
            session_id=meta.get("id"),
        )
        if active_provider.name == "codex"
        else []
    )
    for ordinal, item in enumerate(clean_messages):
        item["clean_ordinal"] = ordinal
        item["source_session_id"] = meta.get("id")
    for ordinal, item in enumerate(clean_events):
        item["clean_ordinal"] = ordinal
        item["source_session_id"] = meta.get("id")

    route_note_report = extract_route_note_candidates_for_source(
        messages,
        events=clean_events,
        source_id=source_id,
        source_thread_key=source_thread_key,
    )
    clean_route_notes = list(route_note_report.get("rows") or [])
    for ordinal, item in enumerate(clean_route_notes):
        item["clean_ordinal"] = ordinal
        item["source_session_id"] = meta.get("id")

    messages_path = out / "messages.jsonl"
    atomic_write_jsonl(messages_path, clean_messages)

    profile_outputs, profile_summary = write_clean_source_redaction_profiles(
        clean_messages,
        profiles=redaction_profiles,
        output_dir=out,
        project_root=cwd,
        canonical_messages_path=messages_path,
    )

    turns_path = out / "turns.jsonl"
    atomic_write_jsonl(turns_path, clean_turns)

    events_path = out / "events.jsonl"
    atomic_write_jsonl(events_path, clean_events)

    route_notes_path = out / "route-notes.jsonl"
    atomic_write_jsonl(route_notes_path, clean_route_notes)

    source_texture = materialize_source_texture_sidecar(
        clean_messages, clean_events, clean_route_notes, out, meta.get("id"), profile_summary
    )

    stat = source_path.stat()
    source_sha256 = file_sha256(source_path) if hash_source else None
    source_artifact = {
        "kind": "provider_transcript",
        "provider": active_provider.name,
        "path": str(source_path),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": source_sha256,
    }
    manifest: dict[str, Any] = {
        "schema_version": CLEAN_SOURCE_SCHEMA_VERSION,
        "kind": "aippocampus_clean_source",
        "created_at": now_utc(),
        "cwd": str(cwd),
        "artifact_scope": "global_thread_store" if output_dir is None else "explicit_output_dir",
        "storage_policy": {
            "default": "AIPPOCAMPUS_REGISTRY_DIR or AIPPOCAMPUS_HOME/registry, with legacy CODEX_HOME fallback",
            "explicit_project_local_output": LEGACY_OUTPUT_DIR,
            "why": "Clean source is private cross-project memory; project-local output is explicit compatibility, not the default.",
        },
        "source_id": source_id,
        "source_provider": active_provider.name,
        "source_thread_key": source_thread_key,
        "source_transcript": str(source_path),
        "source_transcript_size": stat.st_size,
        "source_transcript_mtime": stat.st_mtime,
        "source_transcript_sha256": source_sha256,
        "source_artifact": source_artifact,
        "material_class_contract": clean_source_material_contract(),
        "source_rollout": str(source_path),
        "source_rollout_size": stat.st_size,
        "source_rollout_mtime": stat.st_mtime,
        "source_rollout_sha256": source_sha256,
        "session_meta": meta,
        "message_count": len(clean_messages),
        "turn_count": len(clean_turns),
        "event_count": len(clean_events),
        "route_note_count": len(clean_route_notes),
        "route_note_diagnostic_count": route_note_report.get("metrics", {}).get(
            "diagnostic_only_count",
            0,
        ),
        "source_texture_count": source_texture["row_count"],
        "outputs": {
            "messages_jsonl": str(messages_path),
            "turns_jsonl": str(turns_path),
            "events_jsonl": str(events_path),
            "route_notes_jsonl": str(route_notes_path),
            "source_texture_jsonl": source_texture["path"],
            "redaction_profiles": profile_outputs,
        },
        "provider_normalization_loss": provider_normalization_loss,
        "loss_accounting": loss_accounting,
        "redaction_profiles": profile_summary,
        "identity_policy": {
            "stable_join_keys": [
                "source_id",
                "source_ref",
                "turn_id",
                "message_id",
                "event_id",
                "content_sha256",
            ],
            "message_id": "Stable over rebuilds for the same source, raw line, role, phase, and exact text.",
            "turn_id": "Stable over rebuilds for the same source and inferred user turn boundary.",
            "source_ref": "Provider-neutral audit pointer using provider/session/line, without relying on local absolute paths as identity.",
            "semantic_key": "Deterministic normalized-text key for lightweight sidecars; it is not a semantic embedding.",
            "source_id": "Opaque hash of the provider thread key or session id when available, otherwise the resolved private source path.",
            "event_id": "Stable over rebuilds for the same source, raw line, tool event kind, call ref, and payload hash.",
        },
        "upgrade_contract": {
            "principle": "approximate_locate_then_exact_reconstruct",
            "signature_sidecar": {
                "version": SIGNATURE_CONTRACT_VERSION,
                "status": "reserved",
                "default_dir": "signature-sidecar",
                "join_key": "message_id",
                "source_fields": ["semantic_key", "content_sha256", "text"],
                "expected_outputs": ["manifest.json", "signatures.jsonl"],
            },
            "compressed_content_store": {
                "status": "reserved",
                "join_key": "message_id",
                "source_fields": ["raw_start_line", "raw_end_line", "content_sha256"],
            },
        },
        "cleaning_policy": {
            "redaction_default_profile": "raw-private",
            "projection_boundary": "redacted profiles preserve join keys but are not canonical source truth",
            "keeps": [
                "user_message",
                "assistant final_answer",
                "last assistant commentary only when no final_answer exists",
                "structured tool/test behavior events in events.jsonl",
                "source-joined route-note candidates in route-notes.jsonl",
            ],
            "drops": [
                "tool payload text from messages.jsonl",
                "raw tool stdout, full command text, and full tool arguments from events.jsonl",
                "absolute paths and secret-shaped path segments from event breadcrumbs",
                "duplicate visible messages",
                "injected AGENTS instructions",
                "routine commentary when final_answer exists",
            ],
            "rewrites_text": False,
        },
        "route_note_lane_policy": {
            "status": "enabled_for_codex_and_visible_provider_messages",
            "default_file": "route-notes.jsonl",
            "purpose": "navigation-only process route notes for Active Path Packets",
            "taxonomy": route_note_report.get("taxonomy", []),
            "commentary_is_process_evidence_not_source_truth": True,
            "raw_commentary_policy": "not_serialized",
            "source_join_required": True,
            "diagnostic_only_without_adjacent_evidence": True,
            "join_keys": ["source_id", "thread_key", "turn_index", "line", "message_id", "event_id"],
            "boundary": "route notes are bounded navigation rows joined to adjacent evidence; they do not reintroduce routine commentary into clean source and cannot support claims without source reopen.",
        },
        "source_texture_policy": source_texture["policy"],
        "event_lane_policy": {
            "status": "enabled_for_codex_rollouts",
            "default_file": "events.jsonl",
            "purpose": "source-backed behavior traces for tool/test failures and rollout decision shadows",
            "raw_payload_policy": "hash_only",
            "bounded_breadcrumb_fields": [
                "tool_intent",
                "command_family",
                "target_class",
                "test_target_class",
                "failure_family",
                "path_categories",
                "path_extensions",
                "path_fingerprints",
                "repo_relative_breadcrumbs",
                "generated_file",
                "generated_file_reason",
                "critical_operation_family",
            ],
            "join_keys": ["source_id", "source_ref", "event_id", "turn_index", "call_ref"],
            "boundary": "events.jsonl is structured provenance; derived breadcrumbs are bounded enums, counts, hashes, or booleans, not raw process transcript text.",
        },
        "scope_label_policy": {
            "version": SCOPE_LABEL_POLICY_VERSION,
            "labels": list(SCOPE_LABEL_ORDER),
            "method": "deterministic lexical hints over clean visible text",
            "boundary": "scope_labels are navigation/filtering metadata; source text remains the memory truth.",
        },
    }
    manifest_path = out / "manifest.json"
    manifest["outputs"]["manifest_json"] = str(manifest_path)
    atomic_write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--provider",
        default="codex",
        help="Conversation source provider: codex, claude-code, or generic-jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Defaults to the AIppocampus registry thread store; pass .aippocampus/clean-source for project-local output.",
    )
    parser.add_argument("--hash-source", action="store_true")
    parser.add_argument(
        "--redaction-profile",
        dest="redaction_profiles",
        action="append",
        default=[],
        help="Also write an optional clean-source projection profile, e.g. public-export.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    manifest = build_clean_source(
        args.cwd,
        rollout=args.rollout,
        output_dir=args.output_dir,
        hash_source=args.hash_source,
        provider_name=args.provider,
        redaction_profiles=args.redaction_profiles,
    )
    if args.json_output:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"clean source: {manifest['outputs']['manifest_json']}")
        print(
            f"messages: {manifest['outputs']['messages_jsonl']} ({manifest['message_count']} messages)"
        )
        print(f"turns: {manifest['outputs']['turns_jsonl']} ({manifest['turn_count']} turns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
