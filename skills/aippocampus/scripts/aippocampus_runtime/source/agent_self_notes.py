#!/usr/bin/env python3
"""Low-authority foreground-agent margin notes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_text
from aippocampus_runtime.recall.authority import with_trust_fields
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import registry_paths, unique_preserve

AGENT_SELF_NOTE_SCHEMA_VERSION = 1
AGENT_SELF_NOTE_KIND = "agent_self_note"
AGENT_SELF_NOTES_FILE = "agent-self-notes.jsonl"
AGENT_SELF_NOTE_PROJECTION_MAX_CHARS = 280
AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS = 1200
AGENT_SELF_NOTE_MAX_CHARS = AGENT_SELF_NOTE_PROJECTION_MAX_CHARS
AGENT_SELF_NOTE_BOUNDARY = "agent_self_note_not_source_fact"

VALID_TRIGGERS = {"thread_end", "explicit_agent_reflection", "closeout"}
STATE_RECALL_TERMS = {
    "margin",
    "posture",
    "self",
    "self-note",
    "stance",
    "state",
    "thread shape",
    "找回状态",
    "前的状态",
    "上次状态",
    "姿态",
    "自注",
    "边注",
}
STATE_RECALL_CUE_TERMS = {
    "remember",
    "recall",
    "restore",
    "what was",
    "where was",
    "找回",
    "还记得",
    "记得",
    "之前",
    "上次",
    "前的",
}
RAW_PAYLOAD_RE = re.compile(
    r"(?i)\b(tool_use|tool_result|stdout|stderr|traceback|raw payload|"
    r"function_call|arguments_json|stack trace)\b"
)
SAFE_SOURCE_REF_FIELDS = (
    "thread_key",
    "source_id",
    "source_ref",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "source_line",
    "raw_start_line",
    "raw_end_line",
    "phase",
    "title",
)
PUBLIC_SOURCE_REF_FIELDS = (
    "thread_key",
    "source_id",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "phase",
    "title",
)
PUBLIC_SELF_NOTE_SURFACE_FIELDS = (
    "note_id",
    "created_at",
    "thread_key",
    "note_text",
    "trigger",
    "support_level",
    "trust_level",
    "action_grammar",
    "trust_contract",
    "active_recall_surface",
    "retrieval_role",
    "matched_terms",
    "source_boundary",
    "claims_user_fact",
    "claims_world_fact",
    "claims_source_fact",
    "source_reopen_required_before_claim",
    "foreground_projection_max_chars",
    "note_body_private_available",
    "note_body_private_chars",
    "note_body_private_max_chars",
    "note_body_private_default_visible",
    "note_body_private_reopen_required",
)


class AgentSelfNoteRejected(ValueError):
    """The requested self-note would serialize unsafe or empty material."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details)


def default_agent_self_notes_path(
    registry_path: Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / AGENT_SELF_NOTES_FILE
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / AGENT_SELF_NOTES_FILE


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_agent_self_notes(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_agent_self_notes(path: Path) -> list[dict[str, Any]]:
    return [row for row in _load_jsonl(path) if row.get("kind") == AGENT_SELF_NOTE_KIND]


def _clean_source_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in SAFE_SOURCE_REF_FIELDS:
        value = ref.get(key)
        if value in (None, "", []):
            continue
        clean["line" if key == "source_line" else key] = value
    return clean


def _clean_source_refs(refs: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        clean = _clean_source_ref(ref)
        if not clean:
            continue
        marker = tuple(sorted((key, str(value)) for key, value in clean.items()))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(clean)
        if len(out) >= 4:
            break
    return out


def _normalize_note_text(note_text: str) -> str:
    return re.sub(r"\s+", " ", str(note_text or "")).strip()


def _project_note_text(note_text: str) -> str:
    text = _normalize_note_text(note_text)
    if len(text) <= AGENT_SELF_NOTE_PROJECTION_MAX_CHARS:
        return text
    return text[: AGENT_SELF_NOTE_PROJECTION_MAX_CHARS - 4].rstrip() + " ..."


def sanitize_agent_self_note_payload(
    note_text: str,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, str | None, dict[str, Any]]:
    text = _normalize_note_text(note_text)
    if not text:
        raise AgentSelfNoteRejected("agent_self_note_empty")
    if RAW_PAYLOAD_RE.search(text):
        raise AgentSelfNoteRejected("agent_self_note_raw_payload_rejected")
    if len(text) > AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS:
        raise AgentSelfNoteRejected(
            "agent_self_note_too_long",
            max_chars=AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS,
            projection_chars=AGENT_SELF_NOTE_PROJECTION_MAX_CHARS,
            received_chars=len(text),
        )
    sanitized, policy = sanitize_external_model_text(text, project_root=project_root)
    sanitized = _normalize_note_text(sanitized)
    if policy.get("hard_block") or not sanitized:
        raise AgentSelfNoteRejected("agent_self_note_sensitive_material_rejected")
    if RAW_PAYLOAD_RE.search(sanitized):
        raise AgentSelfNoteRejected("agent_self_note_raw_payload_rejected")
    if len(sanitized) > AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS:
        raise AgentSelfNoteRejected(
            "agent_self_note_too_long",
            max_chars=AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS,
            projection_chars=AGENT_SELF_NOTE_PROJECTION_MAX_CHARS,
            received_chars=len(sanitized),
        )
    projection = _project_note_text(sanitized)
    private_body = (
        sanitized
        if len(sanitized) > AGENT_SELF_NOTE_PROJECTION_MAX_CHARS
        else None
    )
    return projection, private_body, policy


def sanitize_agent_self_note_text(
    note_text: str,
    *,
    project_root: str | Path | None = None,
) -> tuple[str, dict[str, Any]]:
    projection, _private_body, policy = sanitize_agent_self_note_payload(
        note_text,
        project_root=project_root,
    )
    return projection, policy


def build_agent_self_note_row(
    *,
    note_text: str,
    thread_key: str,
    source_refs: Iterable[Mapping[str, Any]],
    trigger: str = "explicit_agent_reflection",
    created_at: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    clean_trigger = trigger if trigger in VALID_TRIGGERS else "explicit_agent_reflection"
    cleaned_refs = _clean_source_refs(source_refs)
    sanitized_text, private_body, redaction_policy = sanitize_agent_self_note_payload(
        note_text,
        project_root=project_root,
    )
    timestamp = created_at or now_utc()
    note_id = _stable_id("asn", thread_key, timestamp, sanitized_text, cleaned_refs)
    # Source refs are a route back to the surrounding source neighborhood, not
    # proof of the note's wording or any claim made by the foreground agent.
    row: dict[str, Any] = {
        "kind": AGENT_SELF_NOTE_KIND,
        "schema_version": AGENT_SELF_NOTE_SCHEMA_VERSION,
        "note_id": note_id,
        "created_at": timestamp,
        "thread_key": compact_text(str(thread_key or "unknown-thread"), 160),
        "source_refs": cleaned_refs,
        "source_ref_count": len(cleaned_refs),
        "note_text": sanitized_text,
        "foreground_projection_max_chars": AGENT_SELF_NOTE_PROJECTION_MAX_CHARS,
        "author_role": "foreground_agent",
        "trigger": clean_trigger,
        "authority": "direction_only",
        "support_level": "scent",
        "memory_surface": "memory_atmosphere",
        "use_boundary": "atmosphere_only",
        "truth_boundary": AGENT_SELF_NOTE_BOUNDARY,
        "privacy_profile": "raw-private",
        "claims_user_fact": False,
        "claims_world_fact": False,
        "claims_source_fact": False,
        "source_reopen_required_before_claim": True,
        "clean_source_mutation_allowed": False,
        "formal_memory_eligible": False,
        "foreground_default_visible": False,
        "external_model_calls": False,
        "raw_tool_payload_serialized": False,
        "redaction_policy": {
            "redacted": bool(redaction_policy.get("redacted")),
            "redaction_count": int(redaction_policy.get("redaction_count") or 0),
            "redaction_types": list(redaction_policy.get("redaction_types") or [])[:8],
        },
    }
    if private_body is not None:
        # The longer body gives an explicit reopen path enough nuance without
        # letting passive or active recall quietly become a hidden narrative
        # channel. Default surfaces must continue to read `note_text` only.
        row.update(
            {
                "note_body_private": private_body,
                "note_body_private_chars": len(private_body),
                "note_body_private_max_chars": AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS,
                "note_body_private_available": True,
                "note_body_private_default_visible": False,
                "note_body_private_reopen_required": True,
            }
        )
    else:
        row["note_body_private_available"] = False
    return with_trust_fields(row)


def append_agent_self_note(
    path: Path,
    *,
    note_text: str,
    thread_key: str,
    source_refs: Iterable[Mapping[str, Any]],
    trigger: str = "explicit_agent_reflection",
    created_at: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    rows = load_agent_self_notes(path)
    row = build_agent_self_note_row(
        note_text=note_text,
        thread_key=thread_key,
        source_refs=source_refs,
        trigger=trigger,
        created_at=created_at,
        project_root=project_root,
    )
    rows.append(row)
    write_agent_self_notes(path, rows)
    return row


def _row_search_text(row: Mapping[str, Any]) -> str:
    ref_text = " ".join(
        str(ref.get("title") or ref.get("thread_key") or ref.get("source_ref") or "")
        for ref in row.get("source_refs") or []
        if isinstance(ref, Mapping)
    )
    return " ".join(
        str(value or "")
        for value in (
            row.get("note_text"),
            row.get("note_body_private"),
            row.get("thread_key"),
            row.get("trigger"),
            ref_text,
        )
    )


def _public_text(value: Any, *, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized or "<redacted:sensitive-text>", chars)


def public_agent_self_note_route_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    route: dict[str, Any] = {}
    for key in PUBLIC_SOURCE_REF_FIELDS:
        value = ref.get(key)
        if value in (None, "", []):
            continue
        route[key] = _public_text(value, chars=180) if isinstance(value, str) else value
    return route


def public_agent_self_note_route_refs(
    row: Mapping[str, Any],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    return [
        route
        for ref in row.get("source_refs") or []
        if isinstance(ref, Mapping)
        and (route := public_agent_self_note_route_ref(ref))
    ][:limit]


def public_agent_self_note_surface(row: Mapping[str, Any]) -> dict[str, Any]:
    public = {
        key: row.get(key)
        for key in PUBLIC_SELF_NOTE_SURFACE_FIELDS
        if row.get(key) not in (None, "", [])
    }
    if "note_text" in public:
        public["note_text"] = _public_text(
            public["note_text"],
            chars=AGENT_SELF_NOTE_PROJECTION_MAX_CHARS,
        )
    if "thread_key" in public:
        public["thread_key"] = _public_text(public["thread_key"], chars=180)
    public["source_refs"] = public_agent_self_note_route_refs(row, limit=4)
    return public


def _state_recall_requested(prompt: str) -> bool:
    low = str(prompt or "").casefold()
    return any(term.casefold() in low for term in STATE_RECALL_TERMS) and any(
        cue.casefold() in low for cue in STATE_RECALL_CUE_TERMS
    )


def search_agent_self_notes(
    prompt: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    terms = [
        term.casefold()
        for term in split_query_terms([prompt])
        if len(term.strip()) >= 2
    ]
    state_requested = _state_recall_requested(prompt)
    scored: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for row in rows:
        if row.get("kind") != AGENT_SELF_NOTE_KIND:
            continue
        text = _row_search_text(row).casefold()
        matched = unique_preserve([term for term in terms if term in text], limit=8)
        if not matched and state_requested:
            matched = ["state_recall_cue"]
        elif not matched:
            continue
        copy = with_trust_fields(dict(row))
        copy["matched_terms"] = matched
        copy["active_recall_surface"] = "agent_self_note"
        copy["retrieval_role"] = "memory_atmosphere"
        copy["source_boundary"] = {
            "self_note_is_not_source_fact": True,
            "source_refs_are_reopen_routes_not_proof_of_note": True,
            "source_reopen_required_before_claim": True,
        }
        score = 1 if matched == ["state_recall_cue"] else len(matched) * 2
        scored.append(((score, str(copy.get("created_at") or "")), copy))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[: max(0, int(limit or 0))]]


def main(argv: list[str] | None = None) -> int:
    from importlib import import_module

    cli = import_module("aippocampus_runtime.source.agent_self_note_cli")
    return int(cli.main(argv) or 0)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AGENT_SELF_NOTE_BOUNDARY",
    "AGENT_SELF_NOTE_KIND",
    "AGENT_SELF_NOTE_MAX_CHARS",
    "AGENT_SELF_NOTE_PRIVATE_BODY_MAX_CHARS",
    "AGENT_SELF_NOTE_PROJECTION_MAX_CHARS",
    "AGENT_SELF_NOTES_FILE",
    "AgentSelfNoteRejected",
    "append_agent_self_note",
    "build_agent_self_note_row",
    "default_agent_self_notes_path",
    "load_agent_self_notes",
    "public_agent_self_note_route_ref",
    "public_agent_self_note_route_refs",
    "public_agent_self_note_surface",
    "sanitize_agent_self_note_payload",
    "sanitize_agent_self_note_text",
    "search_agent_self_notes",
    "write_agent_self_notes",
]
